"""
byepy obfuscator - Round 7
New techniques over round 6:
  1. AnnotationStripper: removes ALL type annotations before obfuscation.
     In Python 3.14 PEP 649 causes the compiler to emit __annotate__ lambdas that
     map obfuscated arg names -> builtin types. Stripping annotations kills that leak.
  2. Per-position varying XOR for string encoding: key byte = (K + i*7 + 3) & 0xFF
     instead of a constant K. Breaks single-byte key extraction tools.
  3. Dispatch table moved OUT of the code object (and thus out of dis output).
     It lives in Stage 2 bootstrap source instead; the code object only has LOAD_GLOBAL
     for the scrambled _ft name with no surrounding table-build code.
  4. Context-sensitive opaque dead code: predicates reference real local variables
     and look like legitimate defensive checks (e.g. `if result < 0: return result`
     right after `result = 0`). Deobfuscator cannot prove these are dead without
     tracking variable value ranges.
  5. Everything from round 6 retained: ctypes marshal, anti-trace, co_varnames scrub,
     package consolidation, scrambled CFF, two-stage bootstrap.
Interface: python obfuscator.py <src_path> <dst_path>
"""

import ast
import base64
import hashlib
import lzma
import marshal
import random
import shutil
import sys
import types
import zlib
from pathlib import Path


def make_rng(salt: str) -> random.Random:
    seed = int(hashlib.sha256(f"byepy-r5-rng:{salt}".encode()).hexdigest(), 16) % (2**32)
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


# ---------------------------------------------------------------------------
# co_varnames scrubber
# ---------------------------------------------------------------------------

def _garble_names(n: int, salt: str) -> tuple:
    out = []
    for i in range(n):
        h = hashlib.sha256(f"{salt}:{i}".encode()).hexdigest()[:14]
        out.append("l" + "".join("lI"[int(c, 16) & 1] for c in h))
    return tuple(out)


def scrub_code(code: types.CodeType, salt: str = "") -> types.CodeType:
    import inspect
    child_salt = f"{salt}:{code.co_name}"
    new_consts = tuple(
        scrub_code(c, child_salt) if isinstance(c, types.CodeType) else c
        for c in code.co_consts
    )
    n_params = (code.co_argcount + code.co_kwonlyargcount
                + (1 if code.co_flags & inspect.CO_VARARGS else 0)
                + (1 if code.co_flags & inspect.CO_VARKEYWORDS else 0))
    param_names = code.co_varnames[:n_params]
    local_count = len(code.co_varnames) - n_params
    garbled_locals = _garble_names(local_count, f"{child_salt}:local")
    new_varnames = param_names + garbled_locals
    new_freevars = _garble_names(len(code.co_freevars), f"{child_salt}:free")
    new_cellvars = _garble_names(len(code.co_cellvars), f"{child_salt}:cell")
    new_name = "<lambda>" if code.co_name not in ("<module>", "") else "<module>"
    kwargs = dict(
        co_varnames=new_varnames,
        co_freevars=new_freevars,
        co_cellvars=new_cellvars,
        co_consts=new_consts,
        co_filename="<generated>",
        co_name=new_name,
    )
    if hasattr(code, "co_qualname"):
        kwargs["co_qualname"] = new_name
    return code.replace(**kwargs)


# ---------------------------------------------------------------------------
# AST transforms
# ---------------------------------------------------------------------------

class AnnotationStripper(ast.NodeTransformer):
    """Strip function-signature type annotations before obfuscation.

    Python 3.14 (PEP 649) compiles annotated functions with __annotate__ lambdas that
    map each obfuscated parameter name -> its type. Stripping parameter/return annotations
    kills that info leak without breaking dataclasses (which need class-level AnnAssign).

    We intentionally DO NOT touch class-level annotations (AnnAssign nodes in a class body)
    because @dataclass reads cls.__annotations__ to discover fields.
    """

    def visit_FunctionDef(self, node):
        # Strip argument annotations (parameter types and return type)
        for arg in (node.args.args + node.args.posonlyargs
                    + node.args.kwonlyargs
                    + ([node.args.vararg] if node.args.vararg else [])
                    + ([node.args.kwarg] if node.args.kwarg else [])):
            arg.annotation = None
        # Strip return annotation
        node.returns = None
        self.generic_visit(node)
        return node
    visit_AsyncFunctionDef = visit_FunctionDef


class DocstringStripper(ast.NodeTransformer):
    def _strip(self, body):
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            stripped = body[1:]
            return stripped if stripped else [ast.Pass()]
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
            for arg in (node.args.args + node.args.posonlyargs + node.args.kwonlyargs):
                self.locals.add(arg.arg)
            if node.args.vararg:
                self.locals.add(node.args.vararg.arg)
            if node.args.kwarg:
                self.locals.add(node.args.kwarg.arg)
            self._depth += 1
            self.generic_visit(node)
            self._depth -= 1
    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Name(self, node):
        if self._depth > 0 and isinstance(node.ctx, ast.Store):
            self.locals.add(node.id)

    def visit_For(self, node):
        if self._depth > 0:
            if isinstance(node.target, ast.Name):
                self.locals.add(node.target.id)
            elif isinstance(node.target, ast.Tuple):
                for elt in node.target.elts:
                    if isinstance(elt, ast.Name):
                        self.locals.add(elt.id)
        self.generic_visit(node)

    def visit_Global(self, node):
        for name in node.names:
            self.locals.discard(name)

    def visit_Nonlocal(self, node):
        for name in node.names:
            self.locals.discard(name)


class ScopeAwareRenamer(ast.NodeTransformer):
    def __init__(self, global_map: dict, file_salt: str):
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


# ---------------------------------------------------------------------------
# Dead code injection — context-sensitive opaque predicates
# ---------------------------------------------------------------------------

def _make_context_dead_block(rng, idx, tracked_vars, fn_args):
    """Generate a dead code block using tracked variable values for predicates.

    The predicates look like defensive programming (error checks, bounds guards)
    but are always False given the known values at the injection point. The bodies
    look like legitimate error handling so deobfuscators may keep them, reducing
    readability and AST similarity of recovered code.
    """
    candidates = []

    # Variables assigned a known non-negative integer value
    for var, val in tracked_vars.items():
        if isinstance(val, int) and val >= 0:
            if val == 0:
                candidates.append((f"({var} < -1)", f"return {var}"))
                candidates.append((f"({var} > 0x7FFFFFFF)", f"raise OverflowError({var!r})"))
            else:
                # val > 0: check for impossible negative
                candidates.append((f"({var} < 0)", f"return None"))
                candidates.append((f"({var} > {val * 1000 + 99999})", f"return {var}"))

    # Variables assigned an empty list or dict
    for var, val in tracked_vars.items():
        if isinstance(val, (list, dict)) and len(val) == 0:
            limit = rng.randint(200, 50000)
            candidates.append((f"(len({var}) > {limit})", f"return {var}"))

    # Function args: use NaN-identity trick (always False for non-float)
    for arg in (fn_args or []):
        if arg not in ("self", "cls"):
            candidates.append((f"({arg} is not None and {arg} != {arg})", f"return {arg}"))

    if candidates:
        pred_str, body_str = rng.choice(candidates)
        try:
            dead_body = ast.parse(body_str, mode="exec").body
            pred_node = ast.parse(pred_str, mode="eval").body
            return ast.If(test=pred_node, body=dead_body, orelse=[])
        except SyntaxError:
            pass

    # Fallback: structurally simple predicates that still look like real checks
    fallback_preds = [
        ("(False)", "pass"),
        ("(None is not None)", "pass"),
    ]
    pred_str, body_str = rng.choice(fallback_preds)
    try:
        return ast.If(
            test=ast.parse(pred_str, mode="eval").body,
            body=ast.parse(body_str, mode="exec").body,
            orelse=[],
        )
    except SyntaxError:
        return ast.If(
            test=ast.Constant(value=False),
            body=[ast.Pass()],
            orelse=[],
        )


class DeadCodeInjector(ast.NodeTransformer):
    def __init__(self, rng):
        self.rng = rng
        self._in_fn = False
        self._fn_args = []

    def _inject(self, stmts):
        if len(stmts) <= 1:
            return stmts
        result = []
        # Track variable assignments for context-sensitive predicates
        tracked_vars = {}

        for i, stmt in enumerate(stmts):
            # Update tracked state BEFORE appending the statement
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        v = stmt.value
                        if isinstance(v, ast.Constant):
                            if isinstance(v.value, (int, float, str, bytes, bool)):
                                tracked_vars[target.id] = v.value
                        elif isinstance(v, ast.List) and not v.elts:
                            tracked_vars[target.id] = []
                        elif isinstance(v, ast.Dict) and not v.keys:
                            tracked_vars[target.id] = {}
                        elif isinstance(v, ast.Set) and not v.elts:
                            tracked_vars[target.id] = set()
                        else:
                            # Complex expression — invalidate any prior known value
                            tracked_vars.pop(target.id, None)
            elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
                # After any augmented assignment (+=, etc.) we don't know the value
                tracked_vars.pop(stmt.target.id, None)

            result.append(stmt)

            if i < len(stmts) - 1 and self.rng.random() < 0.75:
                block = _make_context_dead_block(
                    self.rng, i, tracked_vars.copy(), self._fn_args or []
                )
                result.append(block)

        return result

    def visit_FunctionDef(self, node):
        if not self._in_fn:
            self._in_fn = True
            self._fn_args = [
                arg.arg for arg in (node.args.args + node.args.posonlyargs
                                    + node.args.kwonlyargs)
                if arg.arg not in ("self", "cls")
            ]
            node.body = self._inject(node.body)
            self.generic_visit(node)
            self._in_fn = False
            self._fn_args = []
        return node
    visit_AsyncFunctionDef = visit_FunctionDef


# ---------------------------------------------------------------------------
# XOR + base64 string encoder
# ---------------------------------------------------------------------------

class XorStringEncoder(ast.NodeTransformer):
    """Encode string literals with a per-position varying XOR key.

    Round 7 change: key byte for position i is (K + i*7 + 3) & 0xFF, not a constant K.
    This breaks tools that extract a single-byte XOR key from the lambda constant.
    The encoding uses bytes.fromhex() instead of base64.b64decode() to change the
    bytecode pattern.
    """
    def __init__(self, xor_key):
        self.xor_key = xor_key
        self._in_fstring = 0

    def _encode(self, s):
        raw = s.encode("utf-8")
        K = self.xor_key
        # Per-position key: (K + i*7 + 3) & 0xFF
        enc_bytes = bytes((b ^ ((K + i * 7 + 3) & 0xFF)) for i, b in enumerate(raw))
        hex_str = enc_bytes.hex()

        # bytes.fromhex(hex_str) — different bytecode pattern from b64decode
        fromhex_call = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="bytes", ctx=ast.Load()),
                attr="fromhex",
                ctx=ast.Load(),
            ),
            args=[ast.Constant(value=hex_str)],
            keywords=[],
        )
        # Generator: b ^ ((K + i*7 + 3) & 0xFF) for i, b in enumerate(fromhex_result)
        # Build the key expression: (K + i*7 + 3) & 0xFF
        # = (Constant(K) + Name(i)*Constant(7) + Constant(3)) & Constant(0xFF)
        key_expr = ast.BinOp(
            left=ast.BinOp(
                left=ast.BinOp(
                    left=ast.Constant(value=K),
                    op=ast.Add(),
                    right=ast.BinOp(
                        left=ast.Name(id="_i", ctx=ast.Load()),
                        op=ast.Mult(),
                        right=ast.Constant(value=7),
                    ),
                ),
                op=ast.Add(),
                right=ast.Constant(value=3),
            ),
            op=ast.BitAnd(),
            right=ast.Constant(value=0xFF),
        )
        genexp = ast.GeneratorExp(
            elt=ast.BinOp(
                left=ast.Name(id="_b", ctx=ast.Load()),
                op=ast.BitXor(),
                right=key_expr,
            ),
            generators=[ast.comprehension(
                target=ast.Tuple(
                    elts=[
                        ast.Name(id="_i", ctx=ast.Store()),
                        ast.Name(id="_b", ctx=ast.Store()),
                    ],
                    ctx=ast.Store(),
                ),
                iter=ast.Call(
                    func=ast.Name(id="enumerate", ctx=ast.Load()),
                    args=[fromhex_call],
                    keywords=[],
                ),
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


# ---------------------------------------------------------------------------
# Scrambled CFF with XOR-computed state transitions
# ---------------------------------------------------------------------------

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

    n = len(body)
    # Sample n unique labels from a wide range. XOR-chaining in the byte range (0-255)
    # produces ~60-70% collision probability for n>=17, which breaks state machines with
    # large bodies. Unique sampling preserves obfuscation quality without silent bugs.
    labels = rng.sample(range(1000, 65536), n)

    cases = []
    for i, stmt in enumerate(body):
        is_last = (i == n - 1)
        if is_last:
            if ret_val is not None:
                case_body = [
                    stmt,
                    ast.Assign(
                        targets=[ast.Name(id=rv, ctx=ast.Store())],
                        value=ret_val,
                        lineno=0, col_offset=0,
                    ),
                    ast.Break(),
                ]
            else:
                case_body = [stmt, ast.Break()]
        else:
            # next state = current ^ xor_val (encoded as a constant)
            next_label = labels[i + 1]
            case_body = [
                stmt,
                ast.Assign(
                    targets=[ast.Name(id=sv, ctx=ast.Store())],
                    value=ast.Constant(value=next_label),
                    lineno=0, col_offset=0,
                ),
            ]
        cases.append((labels[i], case_body))

    # Shuffle case presentation order
    shuffled = cases[:]
    rng.shuffle(shuffled)

    def make_test(label):
        return ast.Compare(
            left=ast.Name(id=sv, ctx=ast.Load()),
            ops=[ast.Eq()],
            comparators=[ast.Constant(value=label)],
        )

    def build_chain(idx):
        label, case_body = shuffled[idx]
        if idx < len(shuffled) - 1:
            return ast.If(test=make_test(label), body=case_body,
                          orelse=[build_chain(idx + 1)])
        else:
            return ast.If(test=make_test(label), body=case_body, orelse=[ast.Pass()])

    while_node = ast.While(
        test=ast.Constant(value=True),
        body=[build_chain(0)],
        orelse=[],
    )
    init = ast.Assign(
        targets=[ast.Name(id=sv, ctx=ast.Store())],
        value=ast.Constant(value=labels[0]),
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


# ---------------------------------------------------------------------------
# Builtin dispatch table — replaces RESERVED name refs with _ft[N]() calls
# ---------------------------------------------------------------------------

# Builtins to route through the dispatch table (anchors the deobfuscator uses)
_DISPATCH_TARGETS = frozenset({
    "print", "range", "len", "int", "str", "float", "bool", "list", "dict",
    "set", "tuple", "type", "isinstance", "issubclass", "hasattr", "getattr",
    "setattr", "delattr", "sorted", "reversed", "enumerate", "zip", "map",
    "filter", "min", "max", "sum", "abs", "round", "pow", "divmod",
    "hex", "oct", "bin", "ord", "chr", "format", "id", "hash", "repr",
    "vars", "dir", "callable", "iter", "next", "open", "input",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "RuntimeError", "StopIteration", "NotImplementedError",
    "OSError", "FileNotFoundError", "object", "property", "super",
    "staticmethod", "classmethod",
})


def _encode_builtin_name(name: str, salt: str) -> bytes:
    """XOR-encode a builtin name as bytes literal for the dispatch table."""
    key = int(hashlib.sha256(f"ft:{salt}:{name}".encode()).hexdigest()[:2], 16)
    return bytes(b ^ key for b in name.encode())


def build_dispatch_table_node(names_used: set, salt: str, table_varname: str) -> ast.Assign:
    """
    Build AST for:
        _ft = {
            N: getattr(__import__('builtins'), bytes([...]).decode()),
            ...
        }
    where N is a stable hash-derived integer for each builtin name.
    """
    keys_values = []
    for name in sorted(names_used):
        # Stable integer key for this name
        key_int = int(hashlib.sha256(f"ft_idx:{salt}:{name}".encode()).hexdigest()[:4], 16)
        # Value: getattr(__import__('builtins'), <encoded_name>.decode())
        encoded = _encode_builtin_name(name, salt)
        enc_key = int(hashlib.sha256(f"ft:{salt}:{name}".encode()).hexdigest()[:2], 16)
        # bytes([enc_key ^ b for b in encoded]) == name.encode()
        byte_list = ast.List(
            elts=[ast.Constant(value=b) for b in encoded],
            ctx=ast.Load(),
        )
        # bytes(byte_list)
        bytes_call = ast.Call(
            func=ast.Name(id="bytes", ctx=ast.Load()),
            args=[byte_list],
            keywords=[],
        )
        # XOR each byte back: bytes(b ^ enc_key for b in bytes_call)
        genexp = ast.GeneratorExp(
            elt=ast.BinOp(
                left=ast.Name(id="b", ctx=ast.Load()),
                op=ast.BitXor(),
                right=ast.Constant(value=enc_key),
            ),
            generators=[ast.comprehension(
                target=ast.Name(id="b", ctx=ast.Store()),
                iter=bytes_call,
                ifs=[],
                is_async=0,
            )],
        )
        decoded_bytes_call = ast.Call(
            func=ast.Name(id="bytes", ctx=ast.Load()),
            args=[genexp],
            keywords=[],
        )
        decode_call = ast.Call(
            func=ast.Attribute(value=decoded_bytes_call, attr="decode", ctx=ast.Load()),
            args=[],
            keywords=[],
        )
        # getattr(__import__('builtins'), decode_call)
        getattr_call = ast.Call(
            func=ast.Name(id="getattr", ctx=ast.Load()),
            args=[
                ast.Call(
                    func=ast.Name(id="__import__", ctx=ast.Load()),
                    args=[ast.Constant(value="builtins")],
                    keywords=[],
                ),
                decode_call,
            ],
            keywords=[],
        )
        keys_values.append((ast.Constant(value=key_int), getattr_call))

    dict_node = ast.Dict(
        keys=[k for k, _ in keys_values],
        values=[v for _, v in keys_values],
    )
    return ast.Assign(
        targets=[ast.Name(id=table_varname, ctx=ast.Store())],
        value=dict_node,
        lineno=0, col_offset=0,
    )


class BuiltinDispatcher(ast.NodeTransformer):
    """Replace RESERVED builtin name references with _ft[N]() calls."""

    def __init__(self, salt: str, table_varname: str):
        self.salt = salt
        self.table_varname = table_varname
        self.names_used: set = set()
        self._in_annotation = 0
        self._in_import = False

    def _key_for(self, name: str) -> int:
        return int(hashlib.sha256(f"ft_idx:{self.salt}:{name}".encode()).hexdigest()[:4], 16)

    def _dispatch_ref(self, name: str) -> ast.Subscript:
        self.names_used.add(name)
        return ast.Subscript(
            value=ast.Name(id=self.table_varname, ctx=ast.Load()),
            slice=ast.Constant(value=self._key_for(name)),
            ctx=ast.Load(),
        )

    def visit_Import(self, node):
        return node  # don't touch imports

    def visit_ImportFrom(self, node):
        return node

    def visit_FunctionDef(self, node):
        # Don't replace names in function *signature* annotations
        self._in_annotation += 1
        new_args = node.args
        self._in_annotation -= 1
        self.generic_visit(node)
        return node

    def visit_AnnAssign(self, node):
        self._in_annotation += 1
        self.generic_visit(node)
        self._in_annotation -= 1
        return node

    def visit_Name(self, node):
        if self._in_annotation:
            return node
        if (isinstance(node.ctx, ast.Load)
                and node.id in _DISPATCH_TARGETS):
            return ast.copy_location(self._dispatch_ref(node.id), node)
        return node

    def visit_Attribute(self, node):
        # Visit children (e.g., the object of an attribute access) but don't
        # replace attribute names themselves
        self.generic_visit(node)
        return node

    def visit_ExceptHandler(self, node):
        # Don't replace exception type names used in `except ExcType:`
        # (those are class references, not calls, but still Names)
        if node.type is not None and isinstance(node.type, ast.Name):
            # leave the exception type name intact but still visit the body
            node.body = [self.visit(s) for s in node.body]
            return node
        self.generic_visit(node)
        return node


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def obfuscate_source_ast(source: str, filename: str):
    """Obfuscate source at the AST level.

    Returns (obf_source_str, ft_varname, key_map) where key_map maps each used
    builtin name to its integer lookup key.  The dispatch table is NOT inserted
    into the AST — it lives in the Stage 2 bootstrap to keep the code object clean.
    """
    tree = ast.parse(source, filename=filename)
    rng = make_rng(filename)
    file_salt = hashlib.sha256(f"byepy-r7:{filename}".encode()).hexdigest()[:20]
    xor_key = int(file_salt[:2], 16)
    global_names = collect_global_function_names(tree)
    global_map = {n: scramble_name(n, file_salt) for n in global_names}

    # Strip annotations first — kills PEP 649 __annotate__ lambda info leak
    tree = AnnotationStripper().visit(tree)
    ast.fix_missing_locations(tree)
    # Strip docstrings
    tree = DocstringStripper().visit(tree)
    ast.fix_missing_locations(tree)
    # Rename globals + locals
    tree = ScopeAwareRenamer(global_map, file_salt).visit(tree)
    ast.fix_missing_locations(tree)
    # Dead code with context-sensitive predicates
    tree = DeadCodeInjector(rng).visit(tree)
    ast.fix_missing_locations(tree)
    # CFF (scrambled state machine)
    tree = CFFTransformer(rng).visit(tree)
    ast.fix_missing_locations(tree)
    # String encoding with per-position varying key
    tree = XorStringEncoder(xor_key).visit(tree)
    ast.fix_missing_locations(tree)

    # Route all builtin calls through _ft[N] — table NOT inserted into AST this round
    ft_varname = scramble_name("_ft", file_salt) or "_ft"
    dispatcher = BuiltinDispatcher(salt=file_salt, table_varname=ft_varname)
    tree = dispatcher.visit(tree)
    ast.fix_missing_locations(tree)

    # Build the key map for stage 2 bootstrap use
    key_map = {
        name: int(hashlib.sha256(f"ft_idx:{file_salt}:{name}".encode()).hexdigest()[:4], 16)
        for name in dispatcher.names_used
    }

    return ast.unparse(tree), ft_varname, key_map


def _encode_builtin_name_s2(name: str, salt: str) -> str:
    """Encode a builtin name for the Stage 2 dispatch table using hex + varying XOR.

    Uses a different encoding scheme from the AST string encoder so one tool
    can't decode both. Key for position i = (K + i*11 + 5) & 0xFF.
    """
    K = int(hashlib.sha256(f"s2_ft:{salt}:{name}".encode()).hexdigest()[:2], 16)
    raw = name.encode("utf-8")
    enc = bytes((b ^ ((K + i * 11 + 5) & 0xFF)) for i, b in enumerate(raw))
    return f"bytes((_b^(({K}+_i*11+5)&255) for _i,_b in enumerate(bytes.fromhex({enc.hex()!r}))).decode()"


def _make_stage2(obf_source: str, file_salt: str, ft_varname: str,
                 key_map: dict) -> str:
    """Build Stage 2 bootstrap source: lzma + ctypes + dispatch table injection.

    Round 7: the dispatch table (_ft) is built here, NOT in the code object.
    The code object is exec'd with a globals dict containing the pre-built table,
    so dis output for the code object has no table-construction instructions.
    """
    code_obj = compile(obf_source, "<generated>", "exec")
    code_obj = scrub_code(code_obj, file_salt)
    raw = lzma.compress(marshal.dumps(code_obj), preset=9)
    key2 = hashlib.sha256(f"s2:{file_salt}".encode()).digest()[:16]
    enc2 = bytes(b ^ key2[i % 16] for i, b in enumerate(raw))

    # Build the dispatch table as Python code for the stage 2 source.
    # Uses hex+varying-XOR encoding (different pattern from the AST string encoder).
    table_lines = []
    if key_map:
        table_lines.append(f"{ft_varname}={{}}")
        for name, key_int in sorted(key_map.items(), key=lambda x: x[1]):
            K = int(hashlib.sha256(f"s2_ft:{file_salt}:{name}".encode()).hexdigest()[:2], 16)
            raw_name = name.encode("utf-8")
            enc_name = bytes((b ^ ((K + i * 11 + 5) & 0xFF)) for i, b in enumerate(raw_name))
            decode_expr = (
                f"bytes(_b^(({K}+_i*11+5)&255)"
                f"for _i,_b in enumerate(bytes.fromhex({enc_name.hex()!r}))).decode()"
            )
            table_lines.append(
                f"{ft_varname}[{key_int}]="
                f"getattr(__import__('builtins'),{decode_expr})"
            )
        table_src = "\n".join(table_lines) + "\n"
    else:
        table_src = ""

    # exec the code object with the dispatch table injected as a global
    exec_globals = (
        f"getattr(__import__('builtins'),'exec')(_code,"
        f"{{'__builtins__':__import__('builtins'),'{ft_varname}':{ft_varname},"
        f"'__name__':'__main__','__file__':'<generated>'}})\n"
        if key_map
        else "getattr(__import__('builtins'),'exec')(_code)\n"
    )

    return (
        f"import ctypes as _C,lzma as _L,sys as _s\n"
        f"if _s.gettrace() is not None or _s.getprofile() is not None:raise SystemExit(1)\n"
        f"_api=_C.pythonapi\n"
        f"_api.PyMarshal_ReadObjectFromString.restype=_C.py_object\n"
        f"_api.PyMarshal_ReadObjectFromString.argtypes=[_C.c_char_p,_C.c_ssize_t]\n"
        f"_D2={enc2!r}\n"
        f"_K2={key2!r}\n"
        f"_raw=_L.decompress(bytes(_b^_K2[_i%16]for _i,_b in enumerate(_D2)))\n"
        f"_code=_api.PyMarshal_ReadObjectFromString(_raw,len(_raw))\n"
        f"del _D2,_K2,_raw,_api\n"
        f"{table_src}"
        f"{exec_globals}"
    )


def make_bootstrap(src_path: Path, obf_source: str, file_salt: str,
                   ft_varname: str = "", key_map: dict = None) -> str:
    """Two-stage bootstrap: Stage 1 (zlib, type-check) -> Stage 2 (lzma, ctypes) -> code."""
    stage2_src = _make_stage2(obf_source, file_salt, ft_varname, key_map or {})
    stage2_bytes = stage2_src.encode("utf-8")
    raw1 = zlib.compress(stage2_bytes, level=9)
    key1 = hashlib.sha256(f"s1:{file_salt}".encode()).digest()[:16]
    enc1 = bytes(b ^ key1[i % 16] for i, b in enumerate(raw1))
    return (
        f"import zlib as _Z,sys as _s\n"
        f"if _s.gettrace() is not None or _s.getprofile() is not None:raise SystemExit(1)\n"
        f"if type(_Z.decompress).__name__!='builtin_function_or_method':raise SystemExit(1)\n"
        f"_D={enc1!r}\n"
        f"_K={key1!r}\n"
        f"_src=_Z.decompress(bytes(_b^_K[_i%16]for _i,_b in enumerate(_D))).decode()\n"
        f"del _D,_K\n"
        f"getattr(__import__('builtins'),'exec')(_src)\n"
    )


def obfuscate_file_bootstrap(src: Path, dst: Path) -> None:
    source = src.read_text(encoding="utf-8")
    file_salt = hashlib.sha256(f"byepy-r7:{src.name}".encode()).hexdigest()[:20]
    obf_source, ft_varname, key_map = obfuscate_source_ast(source, src.name)
    bootstrap = make_bootstrap(src, obf_source, file_salt, ft_varname, key_map)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(bootstrap, encoding="utf-8")


# ---------------------------------------------------------------------------
# Package consolidation — inline all files, bootstrap the combined source
# ---------------------------------------------------------------------------

def _strip_relative_imports(source: str) -> str:
    """Remove lines that are relative imports (from . / from .x / import .x)."""
    lines = source.splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("from .") or stripped.startswith("import ."):
            continue
        out.append(line)
    return "".join(out)


def _strip_main_guards(source: str) -> str:
    """Remove top-level 'if __name__ == \"__main__\":' blocks via AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    def is_main_guard(node):
        return (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Eq)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value == "__main__"
        )

    tree.body = [n for n in tree.body if not is_main_guard(n)]
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _consolidate_package(src_dir: Path) -> str:
    """Read all .py files from a package, strip relative imports, concatenate.
    Non-__main__ files also have their __main__ guard blocks removed so they
    don't execute when included inline in the consolidated module.
    """
    py_files = sorted(src_dir.rglob("*.py"))
    main_files = [f for f in py_files if f.name == "__main__.py"]
    other_files = [f for f in py_files if f.name != "__main__.py"]
    ordered = other_files + main_files

    parts = []
    for f in ordered:
        src = f.read_text(encoding="utf-8")
        src = _strip_relative_imports(src)
        if f.name != "__main__.py":
            src = _strip_main_guards(src)
        parts.append(f"# --- {f.name} ---\n" + src)
    return "\n\n".join(parts)


def obfuscate_package(src_dir: Path, dst_dir: Path) -> None:
    """Consolidate package into one bootstrap __main__.py; write stubs for others."""
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True)

    combined = _consolidate_package(src_dir)
    file_salt = hashlib.sha256(f"byepy-r7:{src_dir.name}".encode()).hexdigest()[:20]
    obf_source, ft_varname, key_map = obfuscate_source_ast(combined, src_dir.name)
    bootstrap = make_bootstrap(src_dir, obf_source, file_salt, ft_varname, key_map)

    (dst_dir / "__main__.py").write_text(bootstrap, encoding="utf-8")

    # Stubs: __init__.py and any other files get empty placeholders
    for orig_file in src_dir.rglob("*.py"):
        rel = orig_file.relative_to(src_dir)
        if rel.name == "__main__.py":
            continue
        stub_path = dst_dir / rel
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        stub_path.write_text("# stub\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <src_path> <dst_path>")
        sys.exit(1)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    if src.is_dir():
        obfuscate_package(src, dst)
    else:
        obfuscate_file_bootstrap(src, dst)
