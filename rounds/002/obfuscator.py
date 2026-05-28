"""
byepy obfuscator — Round 2
Techniques:
  1. Module-level function name renaming (shake_128, new salt)
  2. Scope-aware local variable + parameter renaming per function
  3. Dead code injection (always-false branches with plausible-looking code)
  4. Opaque predicates (always-true guards around real logic)
  5. XOR + base64 string encoding (dual-layer, key derived per file)
Interface: python obfuscator.py <src_path> <dst_path>
"""

import ast
import base64
import hashlib
import os
import random
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Deterministic RNG seeded per file (reproducible builds)
# ---------------------------------------------------------------------------

def make_rng(filename: str) -> random.Random:
    seed = int(hashlib.sha256(f"byepy-r2-rng:{filename}".encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


# ---------------------------------------------------------------------------
# Name scrambler (new salt, harder to reverse-engineer)
# ---------------------------------------------------------------------------

RESERVED = frozenset({
    "None", "True", "False", "self", "cls",
    "__init__", "__main__", "__name__", "__file__", "__all__", "__version__",
    "__doc__", "__str__", "__repr__", "__len__", "__iter__", "__next__",
    "__enter__", "__exit__", "__getitem__", "__setitem__", "__delitem__",
    "__contains__", "__eq__", "__lt__", "__le__", "__gt__", "__ge__",
    "__hash__", "__bool__", "__call__", "__class__", "__dict__",
    "__module__", "__slots__", "__annotations__", "__builtins__",
    "__package__", "__spec__", "__loader__",
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
    "os", "sys", "re", "json", "csv", "io", "ast", "math",
    "pathlib", "Path", "Counter", "defaultdict", "dataclass",
    "field", "asdict", "Optional", "Any", "Iterator",
    "subprocess", "shutil", "tempfile", "textwrap",
})

# Prefix pool — these look like legitimate variable names at a glance
_PREFIXES = ["l", "I", "ll", "lI", "Il", "II", "lll", "llI", "lIl", "Ill"]


def scramble_name(name: str, salt: str) -> str:
    if name in RESERVED or name.startswith("__"):
        return name
    digest = hashlib.shake_128(f"{salt}:{name}".encode()).hexdigest(7)
    # Use a mix of l/I prefix to make visually confusing names
    prefix = _PREFIXES[int(digest[0], 16) % len(_PREFIXES)]
    return f"{prefix}{digest}"


# ---------------------------------------------------------------------------
# Scope-aware renaming: collect locals per function
# ---------------------------------------------------------------------------

class FunctionLocalCollector(ast.NodeVisitor):
    """Collect all locally-defined names within a single function (non-nested)."""

    def __init__(self) -> None:
        self.locals: set[str] = set()
        self._depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._depth == 0:
            self._depth += 1
            # Collect argument names
            for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                self.locals.add(arg.arg)
            if node.args.vararg:
                self.locals.add(node.args.vararg.arg)
            if node.args.kwarg:
                self.locals.add(node.args.kwarg.arg)
            self.generic_visit(node)
            self._depth -= 1
        # Don't descend into nested functions

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.locals.add(node.id)

    def visit_For(self, node: ast.For) -> None:
        # Collect for-loop target variables
        if isinstance(node.target, ast.Name):
            self.locals.add(node.target.id)
        elif isinstance(node.target, ast.Tuple):
            for elt in ast.walk(node.target):
                if isinstance(elt, ast.Name):
                    self.locals.add(elt.id)
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        # Remove global names from locals
        for name in node.names:
            self.locals.discard(name)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self.locals.discard(name)


class ScopeAwareRenamer(ast.NodeTransformer):
    """
    Rename:
      - Module-level function names (globally, uniform)
      - Local variables and params within each function (function-scope salt)
    Does NOT rename inside class bodies (preserves method names and attribute consistency).
    """

    def __init__(self, global_map: dict[str, str], file_salt: str) -> None:
        self.global_map = global_map  # module-level function renames
        self.file_salt = file_salt
        self._local_map: dict[str, str] = {}
        self._in_class: int = 0
        self._in_function: int = 0

    def _enter_function(self, node) -> None:
        """Build and push a local name map for this function."""
        collector = FunctionLocalCollector()
        collector.visit(node)
        fn_salt = f"{self.file_salt}:fn:{node.name}"
        self._local_map = {
            n: scramble_name(n, fn_salt)
            for n in collector.locals
            if n not in RESERVED and not n.startswith("__")
        }

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        if self._in_class:
            # Inside a class: don't rename method name or its internals
            self.generic_visit(node)
            return node

        # Rename the function name at module/function level
        node.name = self.global_map.get(node.name, node.name)

        # Build local map and rename args
        self._enter_function(node)
        saved_local = self._local_map
        self._in_function += 1

        for arg in (node.args.args + node.args.posonlyargs +
                    node.args.kwonlyargs):
            arg.arg = self._local_map.get(arg.arg, arg.arg)
        if node.args.vararg:
            node.args.vararg.arg = self._local_map.get(
                node.args.vararg.arg, node.args.vararg.arg)
        if node.args.kwarg:
            node.args.kwarg.arg = self._local_map.get(
                node.args.kwarg.arg, node.args.kwarg.arg)

        self.generic_visit(node)
        self._in_function -= 1
        self._local_map = saved_local
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        self._in_class += 1
        self.generic_visit(node)
        self._in_class -= 1
        return node

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if self._in_class:
            return node
        if self._in_function:
            node.id = self._local_map.get(node.id,
                       self.global_map.get(node.id, node.id))
        else:
            node.id = self.global_map.get(node.id, node.id)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        self.generic_visit(node)
        return node


# ---------------------------------------------------------------------------
# XOR + base64 string encoding
# ---------------------------------------------------------------------------

def xor_encode(text: str, key: int) -> bytes:
    """XOR each UTF-8 byte with key (single byte, repeated)."""
    data = text.encode("utf-8")
    return bytes(b ^ key for b in data)


class DualLayerStringEncoder(ast.NodeTransformer):
    """
    Encode strings: XOR with file-derived key then base64.
    Decode stub: base64.b64decode(b'...').translate(bytes.maketrans(range(256), [(b^key)%256 for b in range(256)]))
    """

    def __init__(self, xor_key: int) -> None:
        self.xor_key = xor_key
        self._in_fstring: int = 0

    def _build_translate_table(self) -> bytes:
        """Build a 256-byte translate table that XORs each byte with self.xor_key."""
        return bytes((b ^ self.xor_key) % 256 for b in range(256))

    def _encode_string(self, s: str) -> ast.expr:
        encoded_bytes = xor_encode(s, self.xor_key)
        b64 = base64.b64encode(encoded_bytes).decode("ascii")
        table = self._build_translate_table()

        # Build: base64.b64decode(b'...').translate(bytes([...]))
        # Using __import__('base64').b64decode(b'...')
        import_node = ast.Call(
            func=ast.Name(id="__import__", ctx=ast.Load()),
            args=[ast.Constant(value="base64")],
            keywords=[],
        )
        b64decode_attr = ast.Attribute(value=import_node, attr="b64decode", ctx=ast.Load())
        decoded_call = ast.Call(
            func=b64decode_attr,
            args=[ast.Constant(value=b64.encode("ascii"))],
            keywords=[],
        )
        # .translate(bytes([t0, t1, ...]))
        table_node = ast.Call(
            func=ast.Name(id="bytes", ctx=ast.Load()),
            args=[ast.List(elts=[ast.Constant(value=b) for b in table], ctx=ast.Load())],
            keywords=[],
        )
        translated = ast.Call(
            func=ast.Attribute(value=decoded_call, attr="translate", ctx=ast.Load()),
            args=[table_node],
            keywords=[],
        )
        # .decode('utf-8')
        decoded_str = ast.Call(
            func=ast.Attribute(value=translated, attr="decode", ctx=ast.Load()),
            args=[ast.Constant(value="utf-8")],
            keywords=[],
        )
        return decoded_str

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.JoinedStr:
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
# Dead code injection + opaque predicates
# ---------------------------------------------------------------------------

# Pool of always-false opaque conditions (mathematically guaranteed false)
_FALSE_PREDICATES = [
    "(__import__('sys').version_info.major ** 2 + 1 < 0)",
    "(__import__('os').getpid() != __import__('os').getpid())",
    "(id(None) != id(None))",
    "(hash(0) + hash(1) == hash(2) and False)",
    "(len([]) > 0 and False)",
]

# Pool of always-true opaque conditions
_TRUE_PREDICATES = [
    "(__import__('sys').version_info.major >= 3)",
    "(id(None) == id(None))",
    "(len([]) >= 0)",
    "(hash(True) == 1)",
    "(__import__('os').getpid() > 0)",
]

# Plausible-looking dead code bodies (these never execute)
_DEAD_BODIES = [
    # Looks like initialisation
    ["_tmp = list(range(8))", "_tmp.sort(reverse=True)", "del _tmp"],
    # Looks like a guard
    ["_flag = False", "if _flag:", "    raise RuntimeError('state error')"],
    # Looks like logging
    ["_msg = 'debug:ok'", "_ = len(_msg)"],
    # Looks like fallback
    ["_fallback = {}", "_fallback.update({'k': None})"],
]


def _build_opaque_false_block(rng: random.Random, dead_idx: int) -> ast.If:
    """Build: if <always_false>: <dead code> (never executed)."""
    pred_str = rng.choice(_FALSE_PREDICATES)
    dead_lines = _DEAD_BODIES[dead_idx % len(_DEAD_BODIES)]
    dead_src = "\n".join(dead_lines)
    try:
        dead_tree = ast.parse(dead_src, mode="exec")
        dead_body = dead_tree.body
    except SyntaxError:
        dead_body = [ast.Pass()]
    pred_tree = ast.parse(pred_str, mode="eval")
    return ast.If(test=pred_tree.body, body=dead_body, orelse=[])


def _build_opaque_true_wrap(rng: random.Random, real_body: list) -> list:
    """Wrap real_body in: if <always_true>: real_body."""
    pred_str = rng.choice(_TRUE_PREDICATES)
    pred_tree = ast.parse(pred_str, mode="eval")
    return [ast.If(test=pred_tree.body, body=real_body, orelse=[ast.Pass()])]


class DeadCodeInjector(ast.NodeTransformer):
    """
    Inject dead code and opaque predicates into function bodies.
    - Inserts always-false dead code blocks between statements
    - Wraps groups of statements in always-true predicates
    """

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self._in_function = False

    def _inject_into_body(self, stmts: list) -> list:
        """Insert dead blocks between every 2 real statements."""
        if len(stmts) <= 1:
            return stmts
        result = []
        for i, stmt in enumerate(stmts):
            result.append(stmt)
            if i < len(stmts) - 1 and self.rng.random() < 0.6:
                result.append(_build_opaque_false_block(self.rng, i))
        return result

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        if not self._in_function:
            self._in_function = True
            # Inject dead code into the function body
            node.body = self._inject_into_body(node.body)
            self.generic_visit(node)
            self._in_function = False
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


# ---------------------------------------------------------------------------
# Collect global (module-level) function names
# ---------------------------------------------------------------------------

def collect_global_function_names(tree: ast.Module) -> set[str]:
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names - RESERVED


# ---------------------------------------------------------------------------
# Main obfuscation pipeline
# ---------------------------------------------------------------------------

def obfuscate_source(source: str, filename: str = "<unknown>") -> str:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        raise ValueError(f"SyntaxError in {filename}: {e}") from e

    rng = make_rng(filename)
    file_salt = hashlib.sha256(f"byepy-r2:{filename}".encode()).hexdigest()[:16]
    xor_key = int(file_salt[:2], 16)  # derive XOR key from salt

    # Step 1: build global name map
    global_names = collect_global_function_names(tree)
    global_map = {n: scramble_name(n, file_salt) for n in global_names}

    # Step 2: scope-aware renaming (functions + locals)
    tree = ScopeAwareRenamer(global_map, file_salt).visit(tree)
    ast.fix_missing_locations(tree)

    # Step 3: dead code injection
    tree = DeadCodeInjector(rng).visit(tree)
    ast.fix_missing_locations(tree)

    # Step 4: dual-layer string encoding
    tree = DualLayerStringEncoder(xor_key).visit(tree)
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
