#!/usr/bin/env python3
"""
Metrics Truth Verification Script
Validates JSONL files against forensic audit classifications.

Usage:
    python verify_metrics_truth.py <jsonl_file>
    python verify_metrics_truth.py logs/benchmarks/benchmark_*.jsonl

Exit codes:
    0 - All metrics pass verification
    1 - Violations found
    2 - File not found or parse error
"""

import json
import sys
import glob
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict

# Add dashboard backend to path for imports
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

try:
    from reliability import (
        NOT_COLLECTED_FIELDS,
        DERIVED_FIELDS,
        CONDITIONAL_FIELDS,
        ReliabilityClass,
        get_reliability,
    )
except ImportError:
    print("ERROR: Could not import reliability module from dashboard/backend/")
    print("Make sure reliability.py exists in dashboard/backend/")
    sys.exit(2)


def is_non_default(value: Any) -> bool:
    """Check if a value is non-default (indicating data was written)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value  # False is default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    if isinstance(value, list):
        return len(value) > 0
    return True


def verify_record(record: Dict[str, Any], line_num: int) -> List[Dict[str, Any]]:
    """
    Verify a single metrics record against forensic audit classifications.
    
    Returns list of violations found.
    """
    violations = []
    
    # Check for NOT_COLLECTED fields with non-default values
    for field in NOT_COLLECTED_FIELDS:
        if field in record:
            value = record[field]
            if is_non_default(value):
                violations.append({
                    "line": line_num,
                    "field": field,
                    "value": str(value)[:50],
                    "reason": "NOT_COLLECTED field has non-default value",
                    "severity": "ERROR",
                })
    
    return violations


def verify_jsonl(filepath: Path) -> Dict[str, Any]:
    """
    Verify a JSONL file for metrics truth.
    
    Returns verification results dictionary.
    """
    results = {
        "file": str(filepath),
        "total_records": 0,
        "violations": [],
        "warnings": [],
        "stats": {
            "real_fields": 0,
            "derived_fields": 0,
            "conditional_fields": 0,
            "not_collected_violations": 0,
        }
    }
    
    if not filepath.exists():
        results["warnings"].append({
            "error": f"File not found: {filepath}"
        })
        return results
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                record = json.loads(line)
                results["total_records"] += 1
                
                # Verify this record
                record_violations = verify_record(record, line_num)
                results["violations"].extend(record_violations)
                results["stats"]["not_collected_violations"] += len(record_violations)
                
                # Count field types
                for field in record.keys():
                    reliability = get_reliability(field)
                    if reliability == ReliabilityClass.REAL:
                        results["stats"]["real_fields"] += 1
                    elif reliability == ReliabilityClass.DERIVED:
                        results["stats"]["derived_fields"] += 1
                    elif reliability == ReliabilityClass.CONDITIONAL:
                        results["stats"]["conditional_fields"] += 1
                
            except json.JSONDecodeError as e:
                results["warnings"].append({
                    "line": line_num,
                    "error": f"JSON parse error: {e}"
                })
    
    return results


def print_results(results: Dict[str, Any], verbose: bool = False) -> None:
    """Print verification results."""
    print(f"\n{'='*60}")
    print(f"File: {results['file']}")
    print(f"{'='*60}")
    print(f"Total records: {results['total_records']}")
    print(f"Violations: {len(results['violations'])}")
    print(f"Warnings: {len(results['warnings'])}")
    
    if results['violations']:
        print(f"\n{'─'*60}")
        print("VIOLATIONS (NOT_COLLECTED fields with data):")
        print(f"{'─'*60}")
        
        # Group by field
        by_field = defaultdict(list)
        for v in results['violations']:
            by_field[v['field']].append(v)
        
        for field, viols in sorted(by_field.items()):
            print(f"\n  {field}: {len(viols)} occurrences")
            if verbose:
                for v in viols[:3]:
                    print(f"    Line {v['line']}: {v['value']}")
                if len(viols) > 3:
                    print(f"    ... and {len(viols) - 3} more")
    
    if results['warnings']:
        print(f"\n{'─'*60}")
        print("WARNINGS:")
        print(f"{'─'*60}")
        for w in results['warnings'][:5]:
            if 'line' in w:
                print(f"  Line {w['line']}: {w['error']}")
            else:
                print(f"  {w['error']}")


def main():
    if len(sys.argv) < 2:
        print("Metrics Truth Verification Script")
        print("Usage: verify_metrics_truth.py <jsonl_file> [--verbose]")
        print("\nExample:")
        print("  python verify_metrics_truth.py logs/benchmarks/benchmark_20260124.jsonl")
        sys.exit(2)
    
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    files = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    
    # Expand globs
    expanded_files = []
    for pattern in files:
        matches = glob.glob(pattern)
        if matches:
            expanded_files.extend(matches)
        else:
            expanded_files.append(pattern)
    
    if not expanded_files:
        print("No files specified")
        sys.exit(2)
    
    total_violations = 0
    total_records = 0
    
    for filepath in expanded_files:
        results = verify_jsonl(Path(filepath))
        print_results(results, verbose)
        total_violations += len(results['violations'])
        total_records += results['total_records']
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Files verified: {len(expanded_files)}")
    print(f"Total records: {total_records}")
    print(f"Total violations: {total_violations}")
    
    if total_violations == 0:
        print("\n✓ All metrics pass truth verification")
        sys.exit(0)
    else:
        print(f"\n✗ Found {total_violations} violations")
        print("  NOT_COLLECTED fields should not contain data.")
        print("  Either remove the data or reclassify the field.")
        sys.exit(1)


if __name__ == "__main__":
    main()
