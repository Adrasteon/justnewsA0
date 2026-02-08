#!/usr/bin/env python3
"""
Script to check for suspicious processing_time patterns in Python files.

This script scans Python files for patterns that might indicate incorrect
processing time calculations, such as:
- processing_time = time.time() - time.time()
- processing_time = time.time() - start_time (where start_time is not defined)

Usage:
    python scripts/check_processing_time.py
"""

import os
import re
import sys
from pathlib import Path


def should_exclude(file_path):
    """Check if a file should be excluded from the scan."""
    excluded_files = ['check_processing_time.py']
    excluded_dirs = ['tests/scripts']

    for excluded_file in excluded_files:
        if excluded_file in file_path:
            return True

    for excluded_dir in excluded_dirs:
        if excluded_dir in file_path.split(os.sep):
            return True

    return False


def find_python_files(directory):
    """Find all Python files in the given directory."""
    python_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                if not should_exclude(file_path):
                    python_files.append(file_path)
    return python_files


def check_processing_time_patterns(file_path):
    """Check a Python file for suspicious processing_time patterns."""
    with open(file_path, encoding='utf-8') as file:
        content = file.read()

    # Pattern 1: processing_time = time.time() - time.time()
    pattern1 = re.compile(r'processing_time\s*=\s*time\.time\(\)\s*-\s*time\.time\(\)')

    # Pattern 2: processing_time = time.time() - start_time (where start_time is not defined)
    pattern2 = re.compile(r'processing_time\s*=\s*time\.time\(\)\s*-\s*start_time')

    # Check for pattern 1
    if pattern1.search(content):
        return True, "Found suspicious processing_time patterns"

    # Check for pattern 2
    if pattern2.search(content):
        # Check if start_time is defined in the file
        if 'start_time = time.time()' not in content:
            return True, "Found suspicious processing_time patterns"

    return False, None


def main():
    """Main function to run the processing time check."""
    repo_root = Path(os.getcwd())
    python_files = find_python_files(repo_root)

    found_issues = False

    for file_path in python_files:
        has_issue, message = check_processing_time_patterns(file_path)
        if has_issue:
            print(f"Issue found in {file_path}: {message}")
            found_issues = True

    if found_issues:
        sys.exit(1)
    else:
        print("No suspicious processing_time patterns found.")
        sys.exit(0)


if __name__ == '__main__':
    main()
