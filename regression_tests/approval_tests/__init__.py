"""
LIMA approval tests
Tests for LIMA 2.x's step-through approval loop: when the app asks before an action, when it
waits, how a No ends the turn, what a replacement instruction does, and the ways the user can
answer (buttons, Y/N keys, the Ctrl+Alt+Y/N hotkeys).

Each test is one module in this package with a ``run(executor)`` function. Modules are found
by discovery (``pkgutil``, sorted by module name), so adding a test means adding one file —
no edits to this file or to the executor. Files are numbered (``test_10_...``,
``test_20_...``) to keep the order stable; modules starting with an underscore (``_common``)
are shared helpers and are not run.
"""

import importlib
import pkgutil
import time

from lima_test_utils import TEST_FAILED, SLEEP_B

# Only test_* modules run. Leading-underscore helper modules (_common) and anything else
# (e.g. __pycache__ entries) are skipped, so helpers can live in the same package.
TEST_MODULE_PREFIX = "test_"


def discover_test_modules():
    """Return this package's test modules, ordered by module name."""
    names = sorted(
        module.name for module in pkgutil.iter_modules(__path__)
        if module.name.startswith(TEST_MODULE_PREFIX) and not module.ispkg
    )
    return [importlib.import_module(f"{__name__}.{name}") for name in names]


def run_all_approval_tests(executor):
    """
    Run every approval test module in order, closing LIMA between tests.

    Each module owns its result line: it calls executor.add_test_result() itself, so a test
    that fails part-way still reports what it saw. LIMA is closed afterwards either way, the
    same isolation the tool/model sweeps use, so one test can't leave an app or popup in the
    next test's way.
    """
    print("\n" + "=" * 60)
    print("TESTING LIMA'S ACTION APPROVAL LOOP")
    print("=" * 60)

    modules = discover_test_modules()
    if not modules:
        message = "No approval test modules were found in approval_tests/"
        executor.add_test_result("Approval Tests", TEST_FAILED, message)
        print(f"  X {message}")
        return

    print(f"Discovered {len(modules)} approval test(s): "
          f"{', '.join(module.__name__.rsplit('.', 1)[-1] for module in modules)}")

    for module in modules:
        result_name = getattr(module, "RESULT_NAME", module.__name__)
        print("\n" + "-" * 50)
        print(f"APPROVAL TEST: {result_name}")
        print("-" * 50)
        try:
            module.run(executor)
        except Exception as error:
            message = f"Approval test raised an unexpected error: {error}"
            executor.add_test_result(result_name, TEST_FAILED, message)
            print(f"  X {message}")
        finally:
            close_error = executor.process_manager.close()
            if close_error:
                executor.add_error(close_error)
            time.sleep(SLEEP_B)
