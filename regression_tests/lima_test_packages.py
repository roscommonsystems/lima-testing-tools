"""
LIMA test packages: shared discovery and runner.

A test package is a folder of ``test_*.py`` modules (``approval_tests/``, ``feature_tests/``,
...). This module finds them and runs them, so a package's ``__init__.py`` is only its
description and adding a test means adding one file.

A test module is one of two shapes:

* **One test** - ``RESULT_NAME`` and ``run(executor)``, which reports exactly one result with
  ``executor.add_test_result(RESULT_NAME, status, message)``.
* **A table of tests** - ``CASES`` (a list), ``case_name(case)`` (the result name of one row)
  and ``run_case(executor, case)``, which reports exactly one result for that row. Use it when
  the same steps repeat over a list (one row per key, per setting), so every row gets its own
  result, its own fresh LIMA and its own retry.

Either shape may set ``RETRY_ON_FAILURE = False`` for a check whose outcome doesn't depend on
the AI model (a version number, a control that is or isn't there): a failure there is not
going to change on a second attempt.

What the runner adds around each test:

* **A fresh LIMA.** LIMA is closed after every test, so one test can't leave an app, a popup or
  a conversation in the next test's way.
* **One retry** (``RETRY_FAILED_TESTS`` in globals.py). What LIMA's model does varies from run
  to run. A failed test is run again; a pass on the second attempt is reported as PASSED and
  marked ``retried``, with the first failure kept in the message.
* **Crash attribution.** If LIMA's crash log changed or its crash window is open when a test
  ends, that test fails and says so. Without this a crash is only noticed at the end of the
  run, with nothing to say which test caused it.
* **Duration**, so a test that has become slow shows up in the report.
"""

import ctypes
import functools
import importlib
import pkgutil
import time
from dataclasses import dataclass
from typing import Callable

from lima_test_utils import (
    TEST_FAILED, SLEEP_B, RETRY_FAILED_TESTS, check_crash_logs, find_windows_by_title,
)

# Only test_* modules run. Leading-underscore helper modules (_common) and anything else are
# skipped, so helpers can live in the same package.
TEST_MODULE_PREFIX = "test_"

# Title of the message box LIMA shows when it has crashed (lima.py show_crash_message).
CRASH_WINDOW_TITLE = "LIMA Crash"

# How much of a crash log goes into a result message. The full text is in the report's
# crash_logs section.
CRASH_LOG_EXCERPT_CHARACTERS = 400


@dataclass
class TestUnit:
    """One thing the runner runs and reports: a whole module, or one row of a module's table."""

    name: str
    run: Callable
    retry: bool


class ResultRecorder:
    """
    Stands in for the executor while one attempt of a test runs.

    It keeps the attempt's results instead of reporting them, so the runner can decide what
    the attempt means (retry it, fail it for a crash) before anything reaches the report.
    Everything else a test asks the executor for (process_manager, ...) is the real thing.
    """

    def __init__(self, executor):
        self._executor = executor
        self.results = []
        self.errors = []

    def add_test_result(self, test_name, status, message, **details):
        result = {"name": test_name, "status": status, "message": message, "details": details}
        self.results.append(result)

    def add_error(self, error_message):
        self.errors.append(error_message)

    def __getattr__(self, name):
        attribute = getattr(self._executor, name)
        return attribute

    @property
    def failed(self):
        has_failure = any(result["status"] == TEST_FAILED for result in self.results)
        return has_failure

    def failure_summary(self):
        """The failed results of this attempt as one line, for the next attempt's message."""
        failures = [result["message"] for result in self.results if result["status"] == TEST_FAILED]
        summary = " | ".join(failures)
        return summary

    def fail_all(self, reason):
        """Turn every result of this attempt into a failure that starts with reason."""
        for result in self.results:
            result["message"] = f"{reason} The test itself reported {result['status']}: {result['message']}"
            result["status"] = TEST_FAILED


# --------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------

def discover_test_modules(package):
    """
    Import a package's test modules, ordered by module name.

    A module that can't be imported must not take the rest of its package down with it, so it
    is returned separately for the runner to report as a failed test.

    Returns:
        (modules, broken) where broken is a list of (module name, error).
    """
    names = sorted(
        module.name for module in pkgutil.iter_modules(package.__path__)
        if module.name.startswith(TEST_MODULE_PREFIX) and not module.ispkg
    )
    modules = []
    broken = []
    for name in names:
        module_path = f"{package.__name__}.{name}"
        try:
            modules.append(importlib.import_module(module_path))
        except Exception as error:
            broken.append((name, error))
    return modules, broken


def test_units(module):
    """The TestUnits of one test module: one for a single test, one per row for a table."""
    retry = bool(getattr(module, "RETRY_ON_FAILURE", True))
    cases = getattr(module, "CASES", None)
    if cases is None:
        result_name = getattr(module, "RESULT_NAME", module.__name__)
        units = [TestUnit(name=result_name, run=module.run, retry=retry)]
        return units
    units = []
    for case in cases:
        run_this_case = functools.partial(module.run_case, case=case)
        units.append(TestUnit(name=module.case_name(case), run=run_this_case, retry=retry))
    return units


# --------------------------------------------------------------------------------------
# Crash attribution
# --------------------------------------------------------------------------------------

def _crash_log(executor):
    """LIMA's crash log as check_crash_logs returns it ({'exists': False} when there is none)."""
    crash_info = check_crash_logs(executor.process_manager.install_path)
    return crash_info


def _crash_window_open():
    """True while LIMA's crash message box is on screen."""
    for hwnd, _title in find_windows_by_title(CRASH_WINDOW_TITLE):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
    return False


def _crash_evidence(executor, crash_log_before):
    """
    What shows LIMA crashed since crash_log_before was read, or None.

    Call it before closing LIMA: ending the process takes the crash window with it.
    """
    crash_log_now = _crash_log(executor)
    log_changed = (crash_log_now.get("exists")
                   and crash_log_now.get("contents") != crash_log_before.get("contents"))
    if log_changed:
        contents = crash_log_now.get("contents") or ""
        executor.reporter.set_crash_log_info(True, crash_log_now.get("path"), contents)
        excerpt = " ".join(contents[-CRASH_LOG_EXCERPT_CHARACTERS:].split())
        evidence = f"its crash log {crash_log_now.get('path')} changed; it ends: {excerpt!r}"
        return evidence
    if _crash_window_open():
        evidence = f"its {CRASH_WINDOW_TITLE!r} window was open"
        return evidence
    return None


# --------------------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------------------

def _attempt(executor, unit):
    """Run a unit once in the LIMA it starts, then close that LIMA. Returns its ResultRecorder."""
    recorder = ResultRecorder(executor)
    crash_log_before = _crash_log(executor)
    crash = None
    try:
        unit.run(recorder)
    except Exception as error:
        message = f"The test raised an unexpected error: {error}"
        recorder.add_test_result(unit.name, TEST_FAILED, message)
    finally:
        try:
            crash = _crash_evidence(executor, crash_log_before)
        except Exception as error:
            print(f"  ! Could not check whether LIMA crashed: {error}")
        close_error = executor.process_manager.close()
        if close_error:
            recorder.add_error(close_error)
        time.sleep(SLEEP_B)

    if not recorder.results:
        message = "The test finished without reporting a result"
        recorder.add_test_result(unit.name, TEST_FAILED, message)
    if crash:
        crash_reason = f"LIMA crashed during this test: {crash}."
        recorder.fail_all(crash_reason)
        crash_error = f"LIMA crashed during {unit.name}"
        recorder.add_error(crash_error)
    return recorder


def _report(executor, recorder, area, duration_seconds, earlier_failures):
    """Send the final attempt's results to the report, with what earlier attempts saw."""
    attempts = len(earlier_failures) + 1
    for result in recorder.results:
        message = result["message"]
        if earlier_failures:
            earlier = " | ".join(f"attempt {number}: {failure}"
                                 for number, failure in enumerate(earlier_failures, start=1))
            if result["status"] == TEST_FAILED:
                message = f"{message} [failed on all {attempts} attempts; {earlier}]"
            else:
                message = f"{message} [on attempt {attempts}; before that it failed - {earlier}]"
        details = dict(result["details"])
        details.setdefault("area", area)
        details["duration_seconds"] = duration_seconds
        details["retried"] = bool(earlier_failures)
        executor.add_test_result(result["name"], result["status"], message, **details)
    for error_message in recorder.errors:
        executor.add_error(error_message)


def run_unit(executor, unit, area):
    """Run one unit, retrying a failure as RETRY_FAILED_TESTS allows, and report it."""
    attempts_allowed = 1 + (RETRY_FAILED_TESTS if unit.retry else 0)
    earlier_failures = []
    started = time.time()
    recorder = None
    for attempt_number in range(1, attempts_allowed + 1):
        recorder = _attempt(executor, unit)
        if not recorder.failed or attempt_number == attempts_allowed:
            break
        failure = recorder.failure_summary()
        earlier_failures.append(failure)
        print(f"  Attempt {attempt_number} failed; running it again in a fresh LIMA. It reported: {failure}")
    duration_seconds = time.time() - started
    _report(executor, recorder, area, duration_seconds, earlier_failures)


def run_test_package(executor, package, title, area):
    """
    Run every test in a package, in module-name order.

    Args:
        executor: the LimaTestExecutor driving the run.
        package: the imported test package (e.g. the feature_tests module).
        title: the banner printed before the package's tests.
        area: the area its results are filed under in the report.
    """
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

    modules, broken = discover_test_modules(package)
    for name, error in broken:
        message = f"Could not import {package.__name__}/{name}.py, so its tests did not run: {error}"
        executor.add_test_result(f"{package.__name__}.{name}", TEST_FAILED, message, area=area)
        print(f"  X {message}")
    if not modules and not broken:
        message = f"No test modules were found in {package.__name__}/"
        executor.add_test_result(package.__name__, TEST_FAILED, message, area=area)
        print(f"  X {message}")
        return

    units = [unit for module in modules for unit in test_units(module)]
    print(f"Discovered {len(units)} test(s) in {len(modules)} module(s): "
          f"{', '.join(module.__name__.rsplit('.', 1)[-1] for module in modules)}")

    for index, unit in enumerate(units, start=1):
        print("\n" + "-" * 50)
        print(f"{area.upper()} TEST {index}/{len(units)}: {unit.name}")
        print("-" * 50)
        run_unit(executor, unit, area)
