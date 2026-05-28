"""
byepy judge — objective fitness checks.

Usage:
    python judge.py <round_dir> <project_root>

Writes: <round_dir>/report_objective.json with behavioural and AST scores.
The human-readability score is provided by the judge LLM subagent and merged
into report.md separately.
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# Behavioural equivalence
# ---------------------------------------------------------------------------

def run_script(script_path: Path, timeout: int = 15) -> tuple[str, int]:
    """Run a Python script, return (stdout, returncode). stderr ignored."""
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip(), result.returncode


def run_package(pkg_dir: Path, timeout: int = 15) -> tuple[str, int]:
    """Run a Python package with -m, return (stdout, returncode)."""
    result = subprocess.run(
        [sys.executable, "-m", pkg_dir.name],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(pkg_dir.parent),
    )
    return result.stdout.strip(), result.returncode


def behavioural_check(original_path: Path, recovered_path: Path, run_as: str) -> dict:
    """
    Return {"pass": bool, "original_out": str, "recovered_out": str, "note": str}.
    pass=True means recovered output matches original — deobfuscator SUCCEEDED.
    """
    try:
        if run_as == "script":
            orig_out, orig_rc = run_script(original_path)
            rec_out, rec_rc = run_script(recovered_path)
        elif run_as == "package":
            orig_out, orig_rc = run_package(original_path)
            rec_out, rec_rc = run_package(recovered_path)
        else:
            return {"pass": False, "note": f"unknown run_as: {run_as}"}
    except subprocess.TimeoutExpired:
        return {"pass": False, "note": "timeout"}
    except Exception as e:
        return {"pass": False, "note": str(e)}

    matched = orig_out == rec_out
    return {
        "pass": matched,
        "original_out": orig_out[:500],
        "recovered_out": rec_out[:500],
        "note": "match" if matched else "output differs",
    }


# ---------------------------------------------------------------------------
# AST similarity
# ---------------------------------------------------------------------------

def ast_node_types(tree: ast.AST) -> list[str]:
    """Return a flat list of all AST node type names via depth-first walk."""
    return [type(node).__name__ for node in ast.walk(tree)]


def ast_similarity(src_a: str, src_b: str) -> float:
    """
    Compare two Python source strings structurally.
    Score = |intersection of node-type multisets| / |union of node-type multisets|.
    Returns 0.0 on parse error.
    """
    try:
        tree_a = ast.parse(src_a)
        tree_b = ast.parse(src_b)
    except SyntaxError:
        return 0.0

    from collections import Counter
    counts_a = Counter(ast_node_types(tree_a))
    counts_b = Counter(ast_node_types(tree_b))

    intersection = sum((counts_a & counts_b).values())
    union = sum((counts_a | counts_b).values())

    return intersection / union if union > 0 else 0.0


def ast_check(original_path: Path, recovered_path: Path) -> dict:
    """Return {"pass": bool, "score": float, "note": str}. pass=True means score>=0.6."""
    try:
        src_orig = original_path.read_text(encoding="utf-8", errors="replace")
        src_rec = recovered_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"pass": False, "score": 0.0, "note": str(e)}

    score = ast_similarity(src_orig, src_rec)
    return {
        "pass": score >= 0.6,
        "score": round(score, 4),
        "note": "above threshold" if score >= 0.6 else "below threshold",
    }


# ---------------------------------------------------------------------------
# Multi-file package helpers
# ---------------------------------------------------------------------------

def collect_py_files(path: Path) -> list[Path]:
    """Return all .py files under path (or [path] if path is a file)."""
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.py"))


def concatenate_sources(paths: list[Path]) -> str:
    """Concatenate multiple .py sources for AST scoring."""
    parts = []
    for p in paths:
        try:
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def score_tier(tier_name: str, meta_files: list[dict], round_dir: Path, project_root: Path) -> dict:
    """Score all files in a tier. Returns tier result dict."""
    results = []
    for entry in meta_files:
        orig_rel = entry["path"]
        run_as = entry["run_as"]
        orig_path = project_root / orig_rel

        # Determine recovered path
        # Obfuscated files live at round_dir/obfuscated/<tier>/<basename>
        # Recovered files live at round_dir/recovered/<tier>/<basename>
        basename = Path(orig_rel).name
        recovered_path = round_dir / "recovered" / tier_name / basename

        file_result: dict = {"file": orig_rel, "behavioural": {}, "ast": {}}

        # Behavioural check
        if orig_path.exists() and recovered_path.exists():
            file_result["behavioural"] = behavioural_check(orig_path, recovered_path, run_as)
        elif not recovered_path.exists():
            file_result["behavioural"] = {"pass": False, "note": "recovered file missing"}
            file_result["ast"] = {"pass": False, "score": 0.0, "note": "recovered file missing"}
            results.append(file_result)
            continue
        else:
            file_result["behavioural"] = {"pass": False, "note": "original file missing"}

        # AST check — for packages, concatenate all .py files
        if run_as == "package":
            orig_files = collect_py_files(orig_path)
            rec_files = collect_py_files(recovered_path)
            src_orig = concatenate_sources(orig_files)
            src_rec = concatenate_sources(rec_files)
            score = ast_similarity(src_orig, src_rec)
            file_result["ast"] = {
                "pass": score >= 0.6,
                "score": round(score, 4),
                "note": "above threshold" if score >= 0.6 else "below threshold",
            }
        else:
            file_result["ast"] = ast_check(orig_path, recovered_path)

        results.append(file_result)

    # Tier passes if ANY file in it passes on a given check
    # (deobfuscator succeeds on a tier if it recovers at least one file)
    any_behavioural = any(r["behavioural"].get("pass", False) for r in results)
    any_ast = any(r["ast"].get("pass", False) for r in results)

    return {
        "files": results,
        "behavioural_pass": any_behavioural,
        "ast_pass": any_ast,
        # readability is filled in by judge agent
        "readability_pass": None,
        "readability_score": None,
    }


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <round_dir> <project_root>")
        sys.exit(1)

    round_dir = Path(sys.argv[1]).resolve()
    project_root = Path(sys.argv[2]).resolve()

    meta_path = project_root / "corpus_meta.json"
    meta = json.loads(meta_path.read_text())

    report = {}
    for tier_name, tier_data in meta.items():
        report[tier_name] = score_tier(tier_name, tier_data["files"], round_dir, project_root)

    out_path = round_dir / "report_objective.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"Objective scores written to {out_path}")

    # Print summary
    for tier, data in report.items():
        b = "PASS" if data["behavioural_pass"] else "fail"
        a = "PASS" if data["ast_pass"] else "fail"
        print(f"  {tier:8s}  behavioural={b}  ast={a}")


if __name__ == "__main__":
    main()
