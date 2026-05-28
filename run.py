"""
byepy run harness.

Usage:
    python run.py <round_number>

1. Creates rounds/<NNN>/ directory structure.
2. Copies current obfuscator.py into rounds/<NNN>/obfuscator.py.
3. Runs obfuscator.py on every corpus file, writing output to rounds/<NNN>/obfuscated/<tier>/.
4. Creates rounds/<NNN>/recovered/<tier>/ directories (deobfuscator subagent fills these).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).parent.resolve()


def round_dir(n: int) -> Path:
    return ROOT / "rounds" / f"{n:03d}"


def run_obfuscator(obf_script: Path, src_path: Path, dst_path: Path, run_as: str) -> bool:
    """
    Call obfuscator.py on a source file/package.
    obfuscator.py interface:
        python obfuscator.py <src> <dst>
    For packages: src is the package directory, dst is the output directory.
    Returns True on success.
    """
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(obf_script), str(src_path), str(dst_path)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print(f"  [!] obfuscator failed on {src_path.name}: {result.stderr[:200]}")
        return False
    return True


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <round_number>")
        sys.exit(1)

    n = int(sys.argv[1])
    rd = round_dir(n)

    if rd.exists():
        print(f"Round {n:03d} directory already exists: {rd}")
        sys.exit(1)

    # Create directory structure
    rd.mkdir(parents=True)
    for tier in ["trivial", "medium", "hard"]:
        (rd / "obfuscated" / tier).mkdir(parents=True)
        (rd / "recovered" / tier).mkdir(parents=True)

    # Copy obfuscator
    obf_src = ROOT / "obfuscator.py"
    obf_dst = rd / "obfuscator.py"
    shutil.copy2(obf_src, obf_dst)
    print(f"Round {n:03d} — obfuscator.py copied")

    # Load corpus meta
    meta = json.loads((ROOT / "corpus_meta.json").read_text())

    # Obfuscate each file
    success_count = 0
    fail_count = 0
    for tier_name, tier_data in meta.items():
        for entry in tier_data["files"]:
            src_rel = entry["path"]
            run_as = entry["run_as"]
            src_path = ROOT / src_rel
            basename = Path(src_rel).name
            dst_path = rd / "obfuscated" / tier_name / basename

            print(f"  Obfuscating [{tier_name}] {basename} ...", end=" ")
            ok = run_obfuscator(obf_dst, src_path, dst_path, run_as)
            if ok:
                print("ok")
                success_count += 1
            else:
                # Fallback: copy original so deobfuscator still has something to work on
                if src_path.is_dir():
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dst_path)
                print("FAILED (copied original as fallback)")
                fail_count += 1

    print(f"\nObfuscation complete: {success_count} ok, {fail_count} failed")
    print(f"Obfuscated files in: {rd}/obfuscated/")
    print(f"Recovered dir ready: {rd}/recovered/")
    print(f"\nNext steps:")
    print(f"  1. Spawn deobfuscator subagent: give it {rd}/recovered/ as output dir")
    print(f"  2. Spawn judge subagent")
    print(f"  3. python judge.py {rd} {ROOT}")


if __name__ == "__main__":
    main()
