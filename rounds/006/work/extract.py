#!/usr/bin/env python3
"""Static extraction of stage 2 marshal code object from obfuscated .py file."""
import sys
import ast
import zlib
import lzma
import marshal
import re
from pathlib import Path


def extract_stage1(path: Path):
    """Return (D, K) bytes for Stage 1."""
    text = path.read_text()
    tree = ast.parse(text)
    # find _D and _K assignments
    D = None
    K = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, bytes):
                if tgt.id == '_D':
                    D = node.value.value
                elif tgt.id == '_K':
                    K = node.value.value
    if D is None or K is None:
        raise ValueError(f"Could not find _D/_K in {path}")
    return D, K


def decrypt_stage1(D, K):
    raw = bytes(b ^ K[i % 16] for i, b in enumerate(D))
    return zlib.decompress(raw).decode()


def extract_stage2(src: str):
    """Return (D2, K2) bytes."""
    tree = ast.parse(src)
    D2 = None
    K2 = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, bytes):
                if tgt.id == '_D2':
                    D2 = node.value.value
                elif tgt.id == '_K2':
                    K2 = node.value.value
    if D2 is None or K2 is None:
        raise ValueError("Could not find _D2/_K2")
    return D2, K2


def decrypt_stage2(D2, K2):
    raw = bytes(b ^ K2[i % 16] for i, b in enumerate(D2))
    return lzma.decompress(raw)


def get_code(path: Path):
    D, K = extract_stage1(path)
    src = decrypt_stage1(D, K)
    D2, K2 = extract_stage2(src)
    raw = decrypt_stage2(D2, K2)
    code = marshal.loads(raw)
    return code, src


if __name__ == '__main__':
    p = Path(sys.argv[1])
    code, src = get_code(p)
    print("=== Stage 1 source ===")
    print(src[:2000])
    print()
    print("=== Code object ===")
    print(code)
    print("co_name:", code.co_name)
    print("co_varnames:", code.co_varnames)
    print("co_names:", code.co_names)
    print("co_consts:", code.co_consts)
