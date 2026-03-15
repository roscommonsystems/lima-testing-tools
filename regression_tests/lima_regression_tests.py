"""
LIMA Regression Test Suite - Entry Point
Tests basic functionality of LIMA Screen Reader by launching and monitoring the application.
Generates a comprehensive JSON report of test results and any crash logs detected.

This module serves as the entry point for the regression test suite.
The implementation has been refactored into three modules:
- lima_test_utils.py: Core utilities for process management, window handling, screenshots, and API integration
- lima_test_reporter.py: Handles test result reporting, verification helpers, and output generation
- lima_test_executor.py: Handles test execution, LIMA process lifecycle management, and test coordination
"""

import os
import sys

from lima_test_executor import LimaTestExecutor


def main():
    """Main entry point for regression test suite."""
    print("Starting LIMA Regression Test Suite...\n")
    
    executor = LimaTestExecutor()
    success = executor.run_tests()
    executor.print_summary()
    
    # Save report to JSON
    report_path = os.path.join(os.path.dirname(__file__), "test_results.json")
    executor.save_report(report_path)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
