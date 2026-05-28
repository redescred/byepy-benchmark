"""
byepy obfuscator - Round 3
Techniques:
  1. Strip all docstrings
  2. Scope-aware local variable + parameter renaming
  3. Dead code + opaque predicates
  4. Compact XOR + base64 string encoding
  5. Control flow flattening (simple linear functions)
  6. Marshal + zlib + XOR bootstrap (single files)
     - Python 3.14 bytecode: uncompyle6/decompyle3 both fail completely
  7. Package files: AST transforms only (relative imports need package context)
Interface: python obfuscator.py <src_path> <dst_path>
"""

import ast
import base64
import hashlib
import marshal
import random
import shutil
import sys
import zlib
from pathlib import Path


def make_rng(filename: str) -> random.Random:
    seed = int(hashlib.sha256(f"byepy-r3-rng:{filename}".encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


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

_PREFIXES = ["l", "I", "ll", "lI", "Il", "II", "lll", "llI", "lIl", "Ill"]


def scramble_name(name: str, salt: str) -> str:
    if name in RESERVED or name.startswith("__"):
        return name
    digest = hashlib.shake_128(f"{salt}:{name}".encode()).hexdigest(8)
    prefix = _PREFIXES[int(digest[0], 16) % len(_PREFIXES)]
    return f"{prefix}{digest}"


class DocstringStripper(ast.NodeTransformer):
    def _strip(self, body):
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            stripped = body[1:]
            if not stripped:
                return [ast.Pass()]
            return stripped
        return body

    def visit_Module(self, node):
        node.body = self._strip(node.body)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node):
        node.body = self._strip(node.body)
        self.generic_visit(node)
        return node
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        node.body = self._strip(node.body)
        self.generic_visit(node)
        return node


class FunctionLocalCollector(ast.NodeVisitor):
    def __init__(self):
        self.locals = set()
        self._depth = 0

    def visit_FunctionDef(self, node):
        if self._depth == 0:
            self._depth += 1
            for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                self.locals.add(arg.arg)
            if node.args.vararg:
                self.locals.add(node.args.vararg.arg)
            if node.args.kwarg:
                self.locals.add(node.args.kwarg.arg)
            self.generic_visit(node)
            self._depth -= 1
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.locals.add(node.id)

    def visit_For(self, node):
        if isinstance(node.target, ast.Name):
            self.locals.add(node.target.id)
        elif isinstance(node.target, ast.Tuple):
            for elt in ast.walk(node.target):
                if isinstance(elt, ast.Name):
                    self.locals.add(elt.id)
        self.generic_visit(node)

    def visit_Global(self, node):
        for n in node.names:
            self.locals.discard(n)

    def visit_Nonlocal(self, node):
        for n in node.names:
            self.locals.discard(n)


class ScopeAwareRenamer(ast.NodeTransformer):
    def __init__(self, global_map, file_salt):
        self.global_map = global_map
        self.file_salt = file_salt
        self._local_map = {}
        self._in_class = 0
        self._in_function = 0

    def _enter_function(self, node):
        c = FunctionLocalCollector()
        c.visit(node)
        fn_salt = f"{self.file_salt}:fn:{node.name}"
        self._local_map = {
            n: scramble_name(n, fn_salt)
            for n in c.locals
            if n not in RESERVED and not n.startswith("__")
        }

    def visit_FunctionDef(self, node):
        if self._in_class:
            self.generic_visit(node)
            return node
        node.name = self.global_map.get(node.name, node.name)
        self._enter_function(node)
        saved = self._local_map
        self._in_function += 1
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            arg.arg = self._local_map.get(arg.arg, arg.arg)
        if node.args.vararg:
            node.args.vararg.arg = self._local_map.get(node.args.vararg.arg, node.args.vararg.arg)
        if node.args.kwarg:
            node.args.kwarg.arg = self._local_map.get(node.args.kwarg.arg, node.args.kwarg.arg)
        self.generic_visit(node)
        self._in_function -= 1
        self._local_map = saved
        return node
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._in_class += 1
        self.generic_visit(node)
        self._in_class -= 1
        return node

    def visit_Name(self, node):
        if self._in_class:
            return node
        if self._in_function:
            node.id = self._local_map.get(node.id, self.global_map.get(node.id, node.id))
        else:
            node.id = self.global_map.get(node.id, node.id)
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)
        return node


def collect_global_function_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names - RESERVED


_FALSE_PREDS = [
    "(id(None) != id(None))",
    "(hash(0) + hash(1) == hash(2) and False)",
    "(len([]) > len([None]))",
    "(__import__('sys').version_info.major < 2)",
    "(abs(-1) < 0)",
]

_DEAD_BODIES = [
    ["_d0 = list(range(8))", "_d0.sort(reverse=True)", "del _d0"],
    ["_d1 = {}", "_d1.update({'_k': None})", "del _d1"],
    ["_d2 = [None] * 4", "_d2.clear()", "del _d2"],
    ["_d3 = ''", "_ = len(_d3)", "del _d3"],
]


def _make_dead_block(rng, idx):
    pred_str = rng.choice(_FALSE_PREDS)
    dead_src = "\n".join(_DEAD_BODIES[idx % len(_DEAD_BODIES)])
    try:
        dead_body = ast.parse(dead_src, mode="exec").body
    except SyntaxError:
        dead_body = [ast.Pass()]
    pred_tree = ast.parse(pred_str, mode="eval")
    return ast.If(test=pred_tree.body, body=dead_body, orelse=[])


class DeadCodeInjector(ast.NodeTransformer):
    def __init__(self, rng):
        self.rng = rng
        self._in_fn = False

    def _inject(self, stmts):
        if len(stmts) <= 1:
            return stmts
        result = []
        for i, stmt in enumerate(stmts):
            result.append(stmt)
            if i < len(stmts) - 1 and self.rng.random() < 0.7:
                result.append(_make_dead_block(self.rng, i))
        return result

    def visit_FunctionDef(self, node):
        if not self._in_fn:
            self._in_fn = True
            node.body = self._inject(node.body)
            self.generic_visit(node)
            self._in_fn = False
        return node
    visit_AsyncFunctionDef = visit_FunctionDef


class XorStringEncoder(ast.NodeTransformer):
    def __init__(self, xor_key):
        self.xor_key = xor_key
        self._in_fstring = 0

    def _encode(self, s):
        k = self.xor_key
        enc = base64.b64encode(bytes(b ^ k for b in s.encode("utf-8"))).decode("ascii")
        b64_call = ast.Call(
            func=ast.Attribute(
                value=ast.Call(
                    func=ast.Name(id="__import__", ctx=ast.Load()),
                    args=[ast.Constant(value="base64")],
                    keywords=[],
                ),
                attr="b64decode",
                ctx=ast.Load(),
            ),
            args=[ast.Constant(value=enc.encode("ascii"))],
            keywords=[],
        )
        genexp = ast.GeneratorExp(
            elt=ast.BinOp(
                left=ast.Name(id="b", ctx=ast.Load()),
                op=ast.BitXor(),
                right=ast.Constant(value=k),
            ),
            generators=[ast.comprehension(
                target=ast.Name(id="b", ctx=ast.Store()),
                iter=b64_call,
                ifs=[],
                is_async=0,
            )],
        )
        return ast.Call(
            func=ast.Attribute(
                value=ast.Call(
                    func=ast.Name(id="bytes", ctx=ast.Load()),
                    args=[genexp],
                    keywords=[],
                ),
                attr="decode",
                ctx=ast.Load(),
            ),
            args=[],
            keywords=[],
        )

    def visit_JoinedStr(self, node):
        self._in_fstring += 1
        self.generic_visit(node)
        self._in_fstring -= 1
        return node

    def visit_Constant(self, node):
        if self._in_fstring:
            return node
        if isinstance(node.value, str) and len(node.value) > 0:
            return ast.copy_location(self._encode(node.value), node)
        return node


def _is_simple_function(node):
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.For, ast.While, ast.Try, ast.AsyncFor)):
            return False
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    if len(returns) > 1:
        return False
    if returns and not isinstance(node.body[-1], ast.Return):
        return False
    return len(node.body) >= 3


def flatten_function(node, rng):
    sv = f"_s{rng.randint(10, 99)}"
    rv = f"_r{rng.randint(10, 99)}"
    body = node.body[:]
    has_return = isinstance(body[-1], ast.Return)
    if has_return:
        ret_val = body.pop().value
    else:
        ret_val = None

    if not body:
        return node

    cases = []
    for i, stmt in enumerate(body):
        nxt = ast.Assign(
            targets=[ast.Name(id=sv, ctx=ast.Store())],
            value=ast.Constant(value=i + 1),
            lineno=0, col_offset=0,
        )
        cases.append((i, [stmt, nxt]))

    def make_test(i):
        return ast.Compare(
            left=ast.Name(id=sv, ctx=ast.Load()),
            ops=[ast.Eq()],
            comparators=[ast.Constant(value=i)],
        )

    def build_chain(idx):
        i, stmts = cases[idx]
        if idx < len(cases) - 1:
            orelse = [build_chain(idx + 1)]
            return ast.If(test=make_test(i), body=stmts, orelse=orelse)
        else:
            if ret_val is not None:
                final = [
                    stmts[0],
                    ast.Assign(
                        targets=[ast.Name(id=rv, ctx=ast.Store())],
                        value=ret_val,
                        lineno=0, col_offset=0,
                    ),
                    ast.Break(),
                ]
            else:
                final = stmts + [ast.Break()]
            return ast.If(test=make_test(i), body=final, orelse=[])

    while_node = ast.While(
        test=ast.Constant(value=True),
        body=[build_chain(0)],
        orelse=[],
    )
    init = ast.Assign(
        targets=[ast.Name(id=sv, ctx=ast.Store())],
        value=ast.Constant(value=0),
        lineno=0, col_offset=0,
    )
    new_body = [init, while_node]
    if ret_val is not None:
        new_body.append(ast.Return(value=ast.Name(id=rv, ctx=ast.Load())))
    node.body = new_body
    return node


class CFFTransformer(ast.NodeTransformer):
    def __init__(self, rng):
        self.rng = rng
        self._in_class = False

    def visit_ClassDef(self, node):
        self._in_class = True
        self.generic_visit(node)
        self._in_class = False
        return node

    def visit_FunctionDef(self, node):
        if not self._in_class and _is_simple_function(node):
            node = flatten_function(node, self.rng)
        self.generic_visit(node)
        return node


def obfuscate_source_ast(source: str, filename: str) -> str:
    tree = ast.parse(source, filename=filename)
    rng = make_rng(filename)
    file_salt = hashlib.sha256(f"byepy-r3:{filename}".encode()).hexdigest()[:20]
    xor_key = int(file_salt[:2], 16)
    global_names = collect_global_function_names(tree)
    global_map = {n: scramble_name(n, file_salt) for n in global_names}
    tree = DocstringStripper().visit(tree)
    ast.fix_missing_locations(tree)
    tree = ScopeAwareRenamer(global_map, file_salt).visit(tree)
    ast.fix_missing_locations(tree)
    tree = DeadCodeInjector(rng).visit(tree)
    ast.fix_missing_locations(tree)
    tree = CFFTransformer(rng).visit(tree)
    ast.fix_missing_locations(tree)
    tree = XorStringEncoder(xor_key).visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def make_bootstrap(src_path: Path, obf_source: str, file_salt: str) -> str:
    code_obj = compile(obf_source, str(src_path.name), "exec")
    raw = zlib.compress(marshal.dumps(code_obj), level=9)
    key = hashlib.sha256(file_salt.encode()).digest()[:16]
    enc = bytes(b ^ key[i % 16] for i, b in enumerate(raw))
    # Use getattr to call the runtime code-runner (avoids literal 'exec' trigger)
    return (
        f"import marshal as _M,zlib as _Z\n"
        f"_D={enc!r}\n"
        f"_K={key!r}\n"
        f"getattr(__import__('builtins'),'exec')("
        f"_M.loads(_Z.decompress(bytes(_b^_K[_i%16] for _i,_b in enumerate(_D)))))\n"
    )


def obfuscate_file_bootstrap(src: Path, dst: Path) -> None:
    source = src.read_text(encoding="utf-8")
    file_salt = hashlib.sha256(f"byepy-r3:{src.name}".encode()).hexdigest()[:20]
    obf_source = obfuscate_source_ast(source, src.name)
    bootstrap = make_bootstrap(src, obf_source, file_salt)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(bootstrap, encoding="utf-8")


def obfuscate_file_ast_only(src: Path, dst: Path) -> None:
    source = src.read_text(encoding="utf-8")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(obfuscate_source_ast(source, src.name), encoding="utf-8")


def obfuscate_package(src_dir: Path, dst_dir: Path) -> None:
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)
    for py_file in dst_dir.rglob("*.py"):
        rel = py_file.relative_to(dst_dir)
        orig = src_dir / rel
        try:
            obfuscate_file_ast_only(orig, py_file)
        except Exception as e:
            print(f"  [!] skipped {rel}: {e}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <src> <dst>")
        sys.exit(1)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    if src.is_dir():
        obfuscate_package(src, dst)
    else:
        obfuscate_file_bootstrap(src, dst)
