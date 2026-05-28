"""Static deobfuscator for round 007 files.

The bootstrap is XOR+zlib. We extract _D and _K via AST and apply
the transformation without ever running the bootstrap code.
"""
import ast
import sys
import zlib
from pathlib import Path


def extract(path: Path) -> str:
    tree = ast.parse(path.read_text())
    data = None
    key = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant):
                if tgt.id == '_D' and isinstance(node.value.value, bytes):
                    data = node.value.value
                elif tgt.id == '_K' and isinstance(node.value.value, bytes):
                    key = node.value.value
    if data is None or key is None:
        raise RuntimeError(f'could not find _D/_K in {path}')
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return zlib.decompress(xored).decode()


if __name__ == '__main__':
    for p in sys.argv[1:]:
        path = Path(p)
        out = extract(path)
        print(f'=== {path} ===')
        print(out)
        print()
