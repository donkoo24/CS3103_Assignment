import sys
import json
import argparse

def evaluate_t1(data):
    errors = []
    
    # Check completeness
    completeness = data.get("final_completeness_pct", 0)
    if completeness < 99.5:
        errors.append(f"Completeness too low: {completeness}% (Gate: >= 99.5%)")
        
    # Check zero-tolerance metrics
    for key in ["duplicates", "stale", "invalid_history_nonfinal", "connection_errors"]:
        val = data.get(key, 0)
        if val > 0:
            errors.append(f"{key} must be 0, found {val}")
            
    # Check coverage
    coverage = data.get("normal_update_coverage_pct", 0)
    if coverage < 99.0:
        errors.append(f"Normal update coverage too low: {coverage}% (Gate: >= 99%)")
        
    return errors

def main():
    parser = argparse.ArgumentParser(description="CI Gate Checker")
    parser.add_argument("json_file", help="Path to the JSON results file")
    parser.add_argument("--profile", required=True, choices=["t1"], help="Test profile to evaluate")
    args = parser.parse_args()

    try:
        with open(args.json_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find results file {args.json_file}")
        sys.exit(1)

    errors = []
    if args.profile == "t1":
        errors = evaluate_t1(data)

    if errors:
        print("\n❌ CI Gate Validation Failed:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("\n✅ CI Gates Passed")
        sys.exit(0)

if __name__ == "__main__":
    main()