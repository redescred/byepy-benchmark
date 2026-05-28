"""
byepy obfuscator — Round 1
Techniques: AST variable/function/class renaming (shake_128) + base64 string literal encoding.
Interface: python obfuscator.py <src_path> <dst_path>
  src_path: file or directory
  dst_path: file or directory (created as needed)
"""

import ast
import base64
import hashlib
import os
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Name scrambler
# ---------------------------------------------------------------------------

RESERVED = frozenset({
    # Python builtins and keywords we must never rename
    "None", "True", "False", "self", "cls", "__init__", "__main__",
    "__name__", "__file__", "__all__", "__version__", "__doc__",
    "__str__", "__repr__", "__len__", "__iter__", "__next__",
    "__enter__", "__exit__", "__getitem__", "__setitem__", "__delitem__",
    "__contains__", "__eq__", "__lt__", "__le__", "__gt__", "__ge__",
    "__hash__", "__bool__", "__call__", "__class__", "__dict__",
    "__module__", "__slots__", "__annotations__",
    # builtins
    "print", "range", "len", "int", "str", "float", "bool", "list",
    "dict", "set", "tuple", "type", "isinstance", "issubclass",
    "hasattr", "getattr", "setattr", "delattr", "super", "object",
    "property", "staticmethod", "classmethod", "open", "input",
    "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "min", "max", "sum", "abs", "round", "pow", "divmod",
    "hex", "oct", "bin", "ord", "chr", "format", "id", "hash",
    "repr", "vars", "dir", "callable", "iter", "next",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "RuntimeError", "StopIteration", "NotImplementedError",
    "OSError", "IOError", "FileNotFoundError", "PermissionError",
    "SystemExit", "KeyboardInterrupt", "BaseException",
    # common imports that must stay readable
    "os", "sys", "re", "json", "csv", "io", "ast", "math",
    "pathlib", "Path", "Counter", "defaultdict", "dataclass",
    "field", "asdict", "Optional", "Any", "Iterator",
    "subprocess", "shutil", "tempfile", "textwrap",
    # dunder patterns
    "__builtins__", "__package__", "__spec__", "__loader__",
})


def scramble_name(name: str, salt: str = "byepy-r1") -> str:
    """Map an identifier to a short deterministic hash name."""
    if name in RESERVED or name.startswith("__"):
        return name
    digest = hashlib.shake_128(f"{salt}:{name}".encode()).hexdigest(6)
    return f"_{digest}"


# ---------------------------------------------------------------------------
# AST transformer
# ---------------------------------------------------------------------------

class RenameTransformer(ast.NodeTransformer):
    """
    Round 1: rename only module-level function names. Applying renaming uniformly
    to all Name references ensures consistency. Classes, local vars, and method
    names are left alone to avoid cross-scope mismatches (especially in packages).
    """

    def __init__(self, name_map: dict[str, str]) -> None:
        self.name_map = name_map

    def visit_Name(self, node: ast.Name) -> ast.Name:
        node.id = self.name_map.get(node.id, node.id)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.name = self.name_map.get(node.name, node.name)
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        # Don't rename classes: they're often referenced across files in packages
        self.generic_visit(node)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        self.generic_visit(node)
        return node


def collect_names(tree: ast.AST) -> set[str]:
    """Collect module-level function names only (safe to rename uniformly)."""
    names = set()
    # Only top-level FunctionDefs (depth 1 = direct children of Module)
    if isinstance(tree, ast.Module):
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
    return names - RESERVED


def build_name_map(names: set[str], salt: str) -> dict[str, str]:
    return {n: scramble_name(n, salt) for n in names if not n.startswith("__")}


# ---------------------------------------------------------------------------
# String encoder
# ---------------------------------------------------------------------------

class StringEncoder(ast.NodeTransformer):
    """
    Replace string literals with base64-decoded equivalents.
    Wraps: 'hello' -> __import__('base64').b64decode(b'aGVsbG8=').decode()
    Skips constants inside JoinedStr (f-strings) — ast.unparse cannot handle
    arbitrary call nodes inside f-string value slots.
    """

    def __init__(self) -> None:
        self._in_fstring: int = 0  # nesting counter

    def _encode_string(self, s: str) -> ast.expr:
        encoded = base64.b64encode(s.encode("utf-8")).decode("ascii")
        import_node = ast.Call(
            func=ast.Name(id="__import__", ctx=ast.Load()),
            args=[ast.Constant(value="base64")],
            keywords=[],
        )
        b64decode = ast.Attribute(value=import_node, attr="b64decode", ctx=ast.Load())
        decode_bytes = ast.Call(
            func=b64decode,
            args=[ast.Constant(value=encoded.encode("ascii"))],
            keywords=[],
        )
        decode_str = ast.Call(
            func=ast.Attribute(value=decode_bytes, attr="decode", ctx=ast.Load()),
            args=[],
            keywords=[],
        )
        return decode_str

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.JoinedStr:
        # Enter f-string context: do NOT encode constants inside here
        self._in_fstring += 1
        self.generic_visit(node)
        self._in_fstring -= 1
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.expr:
        if self._in_fstring:
            return node
        if isinstance(node.value, str) and len(node.value) > 0:
            return ast.copy_location(self._encode_string(node.value), node)
        return node


# ---------------------------------------------------------------------------
# Obfuscate a single file
# ---------------------------------------------------------------------------

def obfuscate_source(source: str, filename: str = "<unknown>") -> str:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        raise ValueError(f"SyntaxError in {filename}: {e}") from e

    # Step 1: rename identifiers
    names = collect_names(tree)
    name_map = build_name_map(names, salt=f"byepy-r1:{filename}")
    tree = RenameTransformer(name_map).visit(tree)
    ast.fix_missing_locations(tree)

    # Step 2: encode string literals
    tree = StringEncoder().visit(tree)
    ast.fix_missing_locations(tree)

    return ast.unparse(tree)


def obfuscate_file(src: Path, dst: Path) -> None:
    source = src.read_text(encoding="utf-8")
    obfuscated = obfuscate_source(source, filename=src.name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(obfuscated, encoding="utf-8")


def obfuscate_package(src_dir: Path, dst_dir: Path) -> None:
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)
    for py_file in dst_dir.rglob("*.py"):
        rel = py_file.relative_to(dst_dir)
        orig = src_dir / rel
        try:
            obfuscate_file(orig, py_file)
        except Exception as e:
            print(f"  [!] skipped {rel}: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <src> <dst>")
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    if src.is_dir():
        obfuscate_package(src, dst)
    else:
        obfuscate_file(src, dst)
