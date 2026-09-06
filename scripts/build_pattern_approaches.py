import json
import sys
from pathlib import Path

# Add scripts directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))
from generate_all_patterns import PATTERNS, TEMPLATE
from update_pattern_languages import CPP_CODES, JAVA_CODES

def generate_brute_approach(slug: str, base: dict) -> dict:
    func_name = base.get("func", "solve()")
    clean_fn = func_name.split("(")[0]

    py_code = [
        f"def {clean_fn}_brute(arr, target=None):",
        "    n = len(arr)",
        "    # Check every combination naively - O(N^2)",
        "    for i in range(n):",
        "        for j in range(i + 1, n):",
        "            if arr[i] + arr[j] == target:",
        "                return [i, j]",
        "    return None"
    ]

    cpp_code = [
        f"vector<int> {clean_fn}Brute(vector<int>& arr, int target) {{",
        "    int n = arr.size();",
        "    // Naive nested scan across all pairs - O(N^2)",
        "    for (int i = 0; i < n; i++) {",
        "        for (int j = i + 1; j < n; j++) {",
        "            if (arr[i] + arr[j] == target) {",
        "                return {i, j};",
        "            }",
        "        }",
        "    }",
        "    return {};",
        "}"
    ]

    java_code = [
        f"public int[] {clean_fn}Brute(int[] arr, int target) {{",
        "    int n = arr.length;",
        "    // Quadratic brute force search - O(N^2)",
        "    for (int i = 0; i < n; i++) {",
        "        for (int j = i + 1; j < n; j++) {",
        "            if (arr[i] + arr[j] == target) {",
        "                return new int[]{i, j};",
        "            }",
        "        }",
        "    }",
        "    return new int[0];",
        "}"
    ]

    arr = base.get("array", [1, 2, 4, 6, 8, 11, 15])
    steps = [
        {
            "line": 2,
            "vars": {"i": 0, "j": 1, "comparisons": 1, "complexity": "O(N^2)"},
            "l": 0, "r": 1, "dead": [],
            "headline": "Brute Force: Check Pair (i=0, j=1)",
            "reason": "Testing arr[0] + arr[1]. Naive approach checks all N*(N-1)/2 pairs without taking advantage of ordering."
        },
        {
            "line": 4,
            "vars": {"i": 0, "j": 2, "comparisons": 2, "complexity": "O(N^2)"},
            "l": 0, "r": 2, "dead": [],
            "headline": "Inner Loop: Move j to index 2",
            "reason": "Scanning j forward. Inner loop does linear scans for every outer index i, causing quadratic time overhead."
        },
        {
            "line": 4,
            "vars": {"i": 1, "j": 2, "comparisons": "N/2", "complexity": "O(N^2)"},
            "l": 1, "r": 2, "dead": [0],
            "headline": "Outer Loop: Increment i=1, reset j=2",
            "reason": "Redundant comparisons accumulate. No state is preserved across loop iterations."
        },
        {
            "line": 5,
            "vars": {"i": 3, "j": 4, "comparisons": "Quadratic Scan", "isMatch": True},
            "l": 3, "r": 4, "dead": [0, 1, 2],
            "headline": "Target Reached at (i=3, j=4)",
            "reason": "Found solution after exhaustive scanning. Time: O(N^2), Space: O(1). TLEs on large LeetCode inputs!"
        }
    ]

    return {
        "complexity": "Time: O(N²) · Space: O(1)",
        "func": f"{clean_fn}_brute",
        "code": py_code,
        "code_cpp": cpp_code,
        "code_java": java_code,
        "type": base.get("type", "array"),
        "array": arr,
        "steps": steps
    }


def generate_best_approach(slug: str, base: dict) -> dict:
    func_name = base.get("func", "solve()")
    clean_fn = func_name.split("(")[0]

    py_code = [
        f"def {clean_fn}_optimal_in_place(arr, target=None):",
        "    # In-place two-pointer / bitwise optimization - O(1) space",
        "    l, r = 0, len(arr) - 1",
        "    while l < r:",
        "        s = arr[l] + arr[r]",
        "        if s == target: return [l, r]",
        "        elif s < target: l += 1",
        "        else: r -= 1",
        "    return None"
    ]

    cpp_code = [
        f"vector<int> {clean_fn}Optimal(vector<int>& arr, int target) {{",
        "    // In-place pointer convergence: O(N) time, O(1) auxiliary memory",
        "    int l = 0, r = arr.size() - 1;",
        "    while (l < r) {",
        "        int s = arr[l] + arr[r];",
        "        if (s == target) return {l, r};",
        "        else if (s < target) l++;",
        "        else r--;",
        "    }",
        "    return {};",
        "}"
    ]

    java_code = [
        f"public int[] {clean_fn}Optimal(int[] arr, int target) {{",
        "    // Space-optimal in-place execution: O(N) time, O(1) memory",
        "    int l = 0, r = arr.length - 1;",
        "    while (l < r) {",
        "        int s = arr[l] + arr[r];",
        "        if (s == target) return new int[]{l, r};",
        "        else if (s < target) l++;",
        "        else r--;",
        "    }",
        "    return new int[0];",
        "}"
    ]

    arr = base.get("array", [1, 2, 4, 6, 8, 11, 15])
    steps = [
        {
            "line": 3,
            "vars": {"l": 0, "r": len(arr)-1, "aux_space": "0 bytes (O(1))", "time": "O(N)"},
            "l": 0, "r": len(arr)-1, "dead": [],
            "headline": "In-Place Pointer Setup (Zero Auxiliary Memory)",
            "reason": "Optimal solution allocates zero extra memory buffers. Pointers l and r converge inwards."
        },
        {
            "line": 5,
            "vars": {"l": 0, "r": len(arr)-1, "sum": arr[0] + arr[-1], "target": 14},
            "l": 0, "r": len(arr)-1, "dead": [],
            "headline": "Constant-Time Decision Step",
            "reason": "Sum exceeds target. In sorted space, arr[r] cannot pair with any valid element. Eliminate in O(1)!"
        },
        {
            "line": 7,
            "vars": {"l": 1, "r": len(arr)-2, "aux_space": "O(1)", "status": "Narrowing search space"},
            "l": 1, "r": len(arr)-2, "dead": [0, len(arr)-1],
            "headline": "Search Space Slashed Efficiently",
            "reason": "Pointers step inwards. Each step drops one impossible candidate definitively without backtracking."
        },
        {
            "line": 6,
            "vars": {"l": 3, "r": 4, "target": 14, "isMatch": True, "verdict": "Production-grade 100% Beats"},
            "l": 3, "r": 4, "dead": [0, 1, 2, 5, 6],
            "headline": "Optimal Match Found in O(N) Time & O(1) Space 🎯",
            "reason": "Solution achieves theoretical lower bound. Zero heap allocations. Perfect interview submission!"
        }
    ]

    return {
        "complexity": "Time: O(N) · Space: O(1) Auxiliary",
        "func": f"{clean_fn}_optimal_in_place",
        "code": py_code,
        "code_cpp": cpp_code,
        "code_java": java_code,
        "type": base.get("type", "array"),
        "array": arr,
        "steps": steps
    }


def main():
    updated_patterns = {}
    for slug, base in PATTERNS.items():
        opt = dict(base)
        opt["complexity"] = "Time: O(N) · Space: O(1)" if slug == "two-pointers" else "Time: O(N) · Space: O(K)"
        opt["code_cpp"] = CPP_CODES.get(slug, base["code"])
        opt["code_java"] = JAVA_CODES.get(slug, base["code"])

        brute = generate_brute_approach(slug, base)
        best = generate_best_approach(slug, base)

        updated_patterns[slug] = {
            "name": slug.replace("-", " ").title(),
            "approaches": {
                "optimal": opt,
                "brute": brute,
                "best": best
            }
        }

    print(f"Generated multi-approach models for {len(updated_patterns)} patterns.")
    return updated_patterns

if __name__ == "__main__":
    main()
