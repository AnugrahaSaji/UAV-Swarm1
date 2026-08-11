
import sys
import json
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.suites import list_suites
    suites = list_suites()
    # Write directly to file to avoid stdout pollution
    with open("benchmark_plan.json", "w", encoding="utf-8") as f:
        json.dump(suites, f, indent=2)
    print(f"Successfully wrote {len(suites)} suites to benchmark_plan.json")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
