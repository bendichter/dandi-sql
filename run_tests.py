#!/usr/bin/env python
"""
DANDI SQL Test Runner

This script runs the comprehensive test suite for the DANDI SQL project.
It includes options for running specific test categories and generating reports.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --basic            # Run only basic search tests
    python run_tests.py --sql              # Run only SQL query tests
    python run_tests.py --performance      # Run only performance tests
    python run_tests.py --regression       # Run only regression tests
    python run_tests.py --coverage         # Run with coverage report
    python run_tests.py --verbose          # Run with verbose output
"""

import os
import sys
import argparse
import django
from django.conf import settings
from django.test.utils import get_runner
from django.core.management import execute_from_command_line


def setup_django():
    """Set up Django environment for testing"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dandi_sql.settings')
    django.setup()


def run_specific_tests(test_pattern, verbosity=1, coverage=False):
    """Run specific test patterns"""
    if coverage:
        try:
            import coverage
            cov = coverage.Coverage()
            cov.start()
        except ImportError:
            print("Coverage module not installed. Install with: pip install coverage")
            coverage = False
    
    # Run the tests
    test_runner = get_runner(settings)()
    failures = test_runner.run_tests([test_pattern], verbosity=verbosity)
    
    if coverage:
        cov.stop()
        cov.save()
        print("\nCoverage Report:")
        cov.report()
        
        # Generate HTML coverage report
        cov.html_report(directory='htmlcov')
        print("\nHTML coverage report generated in 'htmlcov/' directory")
    
    return failures


def main():
    parser = argparse.ArgumentParser(description='Run DANDI SQL tests')
    parser.add_argument('--basic', action='store_true', 
                       help='Run only basic search API tests')
    parser.add_argument('--sql', action='store_true',
                       help='Run only SQL query API tests')
    parser.add_argument('--schema', action='store_true',
                       help='Run only schema API tests')
    parser.add_argument('--models', action='store_true',
                       help='Run only model tests')
    parser.add_argument('--performance', action='store_true',
                       help='Run only performance tests')
    parser.add_argument('--regression', action='store_true',
                       help='Run only regression tests')
    parser.add_argument('--coverage', action='store_true',
                       help='Run with coverage analysis')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Run with verbose output')
    parser.add_argument('--failfast', action='store_true',
                       help='Stop on first failure')
    
    args = parser.parse_args()
    
    setup_django()
    
    verbosity = 2 if args.verbose else 1
    
    # Determine which tests to run
    test_patterns = []
    
    if args.basic:
        test_patterns.append('dandisets.tests.BasicSearchAPITests')
    if args.sql:
        test_patterns.append('dandisets.tests.SqlQueryAPITests')
    if args.schema:
        test_patterns.append('dandisets.tests.SchemaAPITests')
    if args.models:
        test_patterns.append('dandisets.tests.ModelTests')
    if args.performance:
        test_patterns.append('dandisets.tests.PerformanceTests')
    if args.regression:
        test_patterns.append('dandisets.tests.RegressionTests')
    
    # If no specific test type is specified, run all tests
    if not test_patterns:
        test_patterns = ['dandisets.tests']
    
    total_failures = 0
    
    for pattern in test_patterns:
        print(f"\n{'='*60}")
        print(f"Running {pattern}")
        print(f"{'='*60}")
        
        failures = run_specific_tests(pattern, verbosity, args.coverage and pattern == test_patterns[-1])
        total_failures += failures
        
        if failures and args.failfast:
            print(f"\nStopping due to failures in {pattern}")
            break
    
    print(f"\n{'='*60}")
    print(f"Test Summary")
    print(f"{'='*60}")
    
    if total_failures:
        print(f"❌ {total_failures} test(s) failed")
        sys.exit(1)
    else:
        print("✅ All tests passed!")
        sys.exit(0)


if __name__ == '__main__':
    main()
