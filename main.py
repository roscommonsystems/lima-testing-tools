"""
LIMA Testing Suite - Main Entry Point

This is the primary entry point for the LIMA regression testing suite.
Run this file to execute all regression tests.

Usage:
    python main.py

Or use the provided batch file:
    run_regression_tests.bat
"""

import sys
import os

# Add regression_tests directory to path for imports
regression_tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'regression_tests')
sys.path.insert(0, regression_tests_dir)

from lima_regression_tests import main as run_regression_tests


def main():
    """Main entry point for the LIMA Testing Suite."""
    print("Starting LIMA Regression Testing Suite...")
    run_regression_tests()


if __name__ == "__main__":
    main()
