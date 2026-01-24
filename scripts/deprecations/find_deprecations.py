#!/usr/bin/env python3
"""
Script to find deprecation-like patterns in the JustNews codebase.

This script scans Python files for patterns that indicate deprecated usage
and outputs them in a structured format for baseline comparison.
"""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List

# Patterns to detect (pattern: suggestion)
PATTERNS = {
    "\.dict\(\)": "Pydantic v2: prefer model_dump() instead of dict() where appropriate",
    "\.parse_obj\(\)": "Pydantic v2: use model_validate() instead of parse_obj()",
    "\.parse_raw\(\)": "Pydantic v2: use model_validate_json() instead of parse_raw()",
    "\.json\(\)": "Pydantic v2: use model_dump_json() instead of json()",
    "\.copy\(\)": "Pydantic v2: use model_copy() instead of copy()",
    "\.construct\(\)": "Pydantic v2: avoid construct() in favor of proper validation",
    "\.schema\(\)": "Pydantic v2: use model_json_schema() instead of schema()",
    "\.schema_json\(\)": "Pydantic v2: use model_json_schema() instead of schema_json()",
    "\.validate\(\)": "Pydantic v2: use model_validate() instead of validate()",
    "\.from_orm\(\)": "Pydantic v2: use model_validate() with from_attributes=True",
    "\.parse_file\(\)": "Pydantic v2: use model_validate_json() with file operations",
}

def scan_file(file_path: Path, patterns: Dict[str, str]) -> Dict[str, List[Dict[str, str]]]:
    """Scan a single file for deprecation patterns."""
    results = {pattern: [] for pattern in patterns}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                for pattern in patterns:
                    if re.search(pattern, line):
                        results[pattern].append({
                            'path': str(file_path),
                            'line': str(line_num),
                            'content': line.strip()
                        })
    except (UnicodeDecodeError, PermissionError):
        pass
    
    return results

def scan_repo(repo_path: Path = Path('.')) -> Dict[str, List[Dict[str, str]]]:
    """Scan the entire repository for deprecation patterns."""
    all_results = {pattern: [] for pattern in PATTERNS}
    
    for root, dirs, files in os.walk(repo_path):
        # Skip common non-code directories
        dirs[:] = [d for d in dirs if d not in 
                  {'__pycache__', '.git', '.mypy_cache', '.pytest_cache', 'node_modules'}]
        
        for file in files:
            if file.endswith('.py'):
                file_path = Path(root) / file
                file_results = scan_file(file_path, PATTERNS)
                
                for pattern, matches in file_results.items():
                    all_results[pattern].extend(matches)
    
    return all_results

def main():
    parser = argparse.ArgumentParser(
        description='Find deprecation-like patterns in the JustNews codebase'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output file path for the baseline JSON'
    )
    parser.add_argument(
        '--repo-path',
        type=str,
        default='.',
        help='Path to the repository root (default: current directory)'
    )
    
    args = parser.parse_args()
    repo_path = Path(args.repo_path)
    
    if not repo_path.exists():
        print(f"Error: Repository path {repo_path} does not exist")
        return 1
    
    print(f"Scanning repository at {repo_path}...")
    results = scan_repo(repo_path)
    
    # Filter out patterns with no matches
    filtered_results = {k: v for k, v in results.items() if v}
    
    output_data = {
        'patterns': PATTERNS,
        'matches': filtered_results,
        'summary': {
            'total_files_scanned': sum(len(matches) for matches in results.values()),
            'patterns_found': len(filtered_results),
            'total_occurrences': sum(len(matches) for matches in filtered_results.values())
        }
    }
    
    # Write output
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"Baseline written to {args.output}")
    print(f"Found {output_data['summary']['total_occurrences']} occurrences of {output_data['summary']['patterns_found']} patterns")
    
    return 0

if __name__ == '__main__':
    exit(main())
