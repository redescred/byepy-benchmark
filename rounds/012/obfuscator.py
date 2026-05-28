"""
byepy obfuscator - Round 12
New techniques over round 11:
  1. ClosureCaptureTransformer: wraps every function's final return in a
     closure.  The inner function captures the return-value temp variable,
     forcing CPython to emit MAKE_CELL / SET_FUNCTION_ATTRIBUTE(closure)
     bytecode.  scrub_code() garbles co_cellvars (outer) and co_freevars
     (inner) with independent salts, so the free-var name the decompiler
     emits for the inner function never matches any name in the outer scope.
     The decompiled inner function will reference an undefined name ->
     NameError on the first call.
  2. Stage 1 XOR now includes a position-dependent twist: each byte is XOR'd
     with key[i%16] ^ ((i*7+13)&255) instead of just key[i%16].  The
     round-11 extractor's simple b^key[i%16] formula no longer decrypts Stage 1
     correctly; extract.py must be updated.
  Everything from rounds 8-11 retained: position-dependent Stage 2 XOR,
  loop-based _ft and masked _c tables, SHA-256 + algebraic + isinstance +
  sys-module opaque predicates, TryExceptWrapper, Stage 2 as compiled code
  object, co_varnames scrub, user-function trampolining, package consolidation,
  scrambled CFF.
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

def _make_dead_body(rng, pred_vars, fn_args):
    """Build a 2-4 statement dead block body that looks like real error handling.

    Uses a mix of local assignments, raises, and calls so a deobfuscator that
    keeps the dead branch inflates AST node count and hurts readability.
    """
    # Pick a plausible variable to reference in the body (for realism)
    ref = None
    all_names = list(pred_vars.keys()) + [a for a in (fn_args or []) if a not in ("self", "cls")]
    if all_names:
        ref = rng.choice(all_names)

    # Templates: each is a list of source lines to parse as a block
    templates = [
        # assignment + raise
        [
            f"_dead_{rng.randint(10,99)} = 0",
            f"raise RuntimeError('integrity check failed')",
        ],
        # two assignments + raise
        [
            f"_chk = {ref!r} if {ref} is None else None" if ref else "_chk = None",
            f"_msg = 'unexpected state'",
            f"raise ValueError(_msg)",
        ],
        # assignment + conditional raise
        [
            f"_v = {ref!r}" if ref else "_v = None",
            f"if _v is not None:",
            f"    raise RuntimeError('invariant violated')",
        ],
        # three assignments + return
        [
            f"_a = 0",
            f"_b = _a + 1",
            f"_c2 = _b - 1",
            f"return _c2" if rng.random() < 0.5 else "pass",
        ],
    ]
    chosen = rng.choice(templates)
    src = "\n".join(chosen)
    try:
        return ast.parse(src, mode="exec").body
    except SyntaxError:
        return [ast.Pass()]


def _make_context_dead_block(rng, idx, tracked_vars, fn_args):
    """Generate a dead code block using tracked variable values for predicates.

    Round 10: three predicate families:
    1. SHA-256 all-zero prefix (kept from round 9 — requires crypto reasoning).
    2. Algebraic number-theory invariants — always False by modular arithmetic
       but require algebraic reasoning, not just "crypto = pseudo-random":
         (n*(n+1)) % 2 == 1          [consecutive-integer product is always even]
         (n*n - n) % 2 == 1          [n(n-1) always even]
         (n*n + n + 1) % 2 == 0     [n^2+n+1 always odd]
    3. NaN-identity and bounds checks (secondary fallbacks from earlier rounds).
    Bodies are 2-4 statements (multi-statement dead blocks).
    """
    all_vars = list(tracked_vars.keys()) + [a for a in (fn_args or []) if a not in ("self", "cls")]
    candidates = []

    # Family 1: SHA-256 all-zero prefix — requires cryptographic reasoning to remove
    for var in all_vars:
        n_bytes = rng.choice([2, 3, 4])
        zero_bytes = repr(b'\x00' * n_bytes)
        pred = (
            f"(__import__('hashlib').sha256(str({var}).encode()).digest()[:{n_bytes}]"
            f" == {zero_bytes})"
        )
        candidates.append(pred)

    # Family 2: algebraic opaque predicates — always False by number theory.
    # Only safe for variables with known integer values; SHA-256 handles the rest.
    # (n*(n+1)) % 2 == 1: product of consecutive integers is always even
    # (n*n - n) % 2 == 1: n(n-1) is always even
    # (n*n + n + 1) % 2 == 0: n^2+n+1 is always odd
    int_vars = [v for v in tracked_vars if isinstance(tracked_vars[v], int)
                and not isinstance(tracked_vars[v], bool)]
    for var in int_vars:
        choice = rng.randint(0, 2)
        if choice == 0:
            candidates.append(f"(({var}) * (({var}) + 1)) % 2 == 1")
        elif choice == 1:
            candidates.append(f"(({var}) * ({var}) - ({var})) % 2 == 1")
        else:
            candidates.append(f"(({var}) * ({var}) + ({var}) + 1) % 2 == 0")

    # Secondary: integer bounds (always-False given known value)
    for var, val in tracked_vars.items():
        if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
            if val == 0:
                candidates.append(f"({var} < -1)")
                candidates.append(f"({var} > 0x7FFFFFFF)")
            else:
                candidates.append(f"({var} < 0)")
                candidates.append(f"({var} > {val * 1000 + 99999})")

    # Secondary: empty-container len check
    for var, val in tracked_vars.items():
        if isinstance(val, (list, dict)) and len(val) == 0:
            limit = rng.randint(200, 50000)
            candidates.append(f"(len({var}) > {limit})")

    # Family 3: isinstance-based always-False predicates.
    # Python's type system guarantees these are False: int is not float,
    # bool is not str, list is not dict, str is not int.
    isinstance_pairs = [
        ("0", "float"),
        ("True", "str"),
        ("[]", "dict"),
        ("''", "int"),
        ("0", "str"),
        ("1", "list"),
    ]
    for expr, wrong_type in isinstance_pairs:
        candidates.append(f"isinstance({expr}, {wrong_type})")

    # Family 4: sys-module invariant predicates — always False on Python 3.x / 64-bit.
    # sys.version_info < (1, 0): we are Python 3.x, never < 1.0.
    # sys.maxsize < 0: sys.maxsize is always positive.
    # sys.version_info > (99, 0): major version is never 99+.
    sys_preds = [
        "__import__('sys').version_info < (1, 0)",
        "__import__('sys').maxsize < 0",
        "__import__('sys').version_info > (99, 0)",
        "__import__('sys').float_info.max < 0",
    ]
    for sp in sys_preds:
        candidates.append(sp)

    # Secondary: NaN-identity trick for function args
    for arg in (fn_args or []):
        if arg not in ("self", "cls"):
            candidates.append(f"({arg} is not None and {arg} != {arg})")

    # Build the block
    if candidates:
        pred_str = rng.choice(candidates)
        body = _make_dead_body(rng, tracked_vars, fn_args)
        try:
            pred_node = ast.parse(pred_str, mode="eval").body
            return ast.If(test=pred_node, body=body, orelse=[])
        except SyntaxError:
            pass

    # Fallback: sha256 with a literal integer to avoid any name dependency
    lit = rng.randint(1, 9999)
    n_bytes = rng.choice([2, 3, 4])
    zero_bytes = repr(b'\x00' * n_bytes)
    fallback_pred = (
        f"(__import__('hashlib').sha256(str({lit}).encode()).digest()[:{n_bytes}]"
        f" == {zero_bytes})"
    )
    try:
        return ast.If(
            test=ast.parse(fallback_pred, mode="eval").body,
            body=[ast.Pass()],
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

            if i < len(stmts) - 1 and self.rng.random() < 0.90:
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
# TryExceptWrapper — wrap every function body in try/except BaseException: raise
# ---------------------------------------------------------------------------

class TryExceptWrapper(ast.NodeTransformer):
    """Round 11: wrap function bodies in try: <body> except BaseException: raise.

    Semantically transparent — the except clause unconditionally re-raises, so
    observable behaviour is identical.  The wrapper generates CPython 3.14
    exception-table bytecode (COPY + CALL + POP_EXCEPT patterns) that the
    decompiler's exception-table handler cannot yet reconstruct.

    Applied AFTER CFFTransformer so CFF state machines are inside the try block,
    and BEFORE BuiltinDispatcher so 'BaseException' gets dispatched through _ft.
    """

    def _wrap(self, body: list) -> list:
        if not body or (len(body) == 1 and isinstance(body[0], ast.Pass)):
            return body
        handler = ast.ExceptHandler(
            type=ast.Name(id="BaseException", ctx=ast.Load()),
            name=None,
            body=[ast.Raise()],
        )
        ast.copy_location(handler, body[0])
        try_node = ast.Try(
            body=body,
            handlers=[handler],
            orelse=[],
            finalbody=[],
        )
        ast.copy_location(try_node, body[0])
        return [try_node]

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.body = self._wrap(node.body)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


# ---------------------------------------------------------------------------
# ClosureCaptureTransformer — force closure cells on every return path
# ---------------------------------------------------------------------------

class ClosureCaptureTransformer(ast.NodeTransformer):
    """Round 12: inject an inner closure at each function's last return.

    Every function's final `return EXPR` is rewritten as:

        _clXXXX = EXPR
        def _fYYYY():
            return _clXXXX    # _clXXXX is a free variable (closure cell)
        return _fYYYY()

    This forces CPython to emit MAKE_CELL for _clXXXX in the outer function
    and SET_FUNCTION_ATTRIBUTE(closure) for _fYYYY.  scrub_code() later
    garbles co_cellvars and co_freevars with completely independent salts, so
    the name the decompiler emits for the inner function's free variable
    differs from the name used in the outer function.  The decompiled inner
    function references a name that is never defined in the outer scope ->
    NameError on the first call through that path.

    Applied after TryExceptWrapper (so the return lives inside the try body)
    and before XorStringEncoder (no string constants to encode here).
    """

    def __init__(self, rng: random.Random):
        self._rng = rng

    def _wrap_last_return(self, stmts: list) -> list:
        """Replace the last ast.Return in stmts (or recursively inside a Try)."""
        # Scan for a bare return at this level.
        last_idx = None
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, ast.Return):
                last_idx = i

        if last_idx is not None:
            ret = stmts[last_idx]
            val = ret.value if ret.value is not None else ast.Constant(value=None)
            tmp = f"_cl{self._rng.randint(1000, 9999)}"
            fn  = f"_f{self._rng.randint(1000, 9999)}"

            assign = ast.Assign(
                targets=[ast.Name(id=tmp, ctx=ast.Store())],
                value=val,
            )
            ast.copy_location(assign, ret)
            ast.fix_missing_locations(assign)

            inner = ast.FunctionDef(
                name=fn,
                args=ast.arguments(
                    posonlyargs=[], args=[], vararg=None,
                    kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
                ),
                body=[ast.Return(value=ast.Name(id=tmp, ctx=ast.Load()))],
                decorator_list=[],
                returns=None,
            )
            ast.copy_location(inner, ret)
            ast.fix_missing_locations(inner)

            new_ret = ast.Return(
                value=ast.Call(
                    func=ast.Name(id=fn, ctx=ast.Load()),
                    args=[], keywords=[],
                )
            )
            ast.copy_location(new_ret, ret)
            ast.fix_missing_locations(new_ret)

            return (stmts[:last_idx]
                    + [assign, inner, new_ret]
                    + stmts[last_idx + 1:])

        # No bare return at this level — look inside Try bodies.
        new_stmts = []
        for stmt in stmts:
            if isinstance(stmt, ast.Try):
                stmt.body = self._wrap_last_return(stmt.body)
            new_stmts.append(stmt)
        return new_stmts

    def visit_FunctionDef(self, node):
        # Transform this function but do not recurse into any children —
        # the new inner function must not itself be transformed.
        node.body = self._wrap_last_return(node.body)
        ast.fix_missing_locations(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


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
# Integer constant table — moves numeric constants out of the code object
# ---------------------------------------------------------------------------

class ConstantTableizer(ast.NodeTransformer):
    """Replace integer constants (|val| >= 2, not True/False) with _c[key] subscripts.

    The actual values are stored in Stage 2 bootstrap, so they never appear in
    the code object's dis output.  Keys are SHA-256 derived so two files with
    the same constant use different keys.
    """

    def __init__(self, const_varname: str, const_key_map: dict):
        self.const_varname = const_varname
        self.const_key_map = const_key_map   # {int_value: int_key}

    def visit_Constant(self, node):
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            if abs(node.value) >= 2 and node.value in self.const_key_map:
                key = self.const_key_map[node.value]
                return ast.copy_location(
                    ast.Subscript(
                        value=ast.Name(id=self.const_varname, ctx=ast.Load()),
                        slice=ast.Constant(value=key),
                        ctx=ast.Load(),
                    ),
                    node,
                )
        return node


def collect_meaningful_ints(tree: ast.AST) -> set:
    """Return the set of integer constants with |val| >= 2 in the tree."""
    vals = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            if not isinstance(node.value, bool) and abs(node.value) >= 2:
                vals.add(node.value)
    return vals


# ---------------------------------------------------------------------------
# User-function trampoline — folds top-level function names into _ft
# ---------------------------------------------------------------------------

class UserFunctionTrampoline(ast.NodeTransformer):
    """Convert top-level function definitions to dispatch-table entries.

    For each top-level (non-class, non-nested) function whose scrambled name
    appears in *user_func_set*, produces three statements in place of the def:

        def _tmp_XXXX(args): <body_with_ft_calls>
        _ft[key] = _tmp_XXXX
        del _tmp_XXXX

    All Name references to the function elsewhere are already rewritten as
    _ft[key] subscripts by the BuiltinDispatcher (which we extend to include
    user function names before this transformer runs).
    """

    def __init__(self, salt: str, table_varname: str,
                 user_func_set: set, key_for: dict):
        """
        user_func_set: scrambled names of top-level user functions to trampoline.
        key_for:       scrambled_name -> integer dispatch key.
        """
        self.salt = salt
        self.table_varname = table_varname
        self.user_func_set = user_func_set
        self.key_for = key_for
        self._depth = 0  # only trampoline top-level defs

    def visit_ClassDef(self, node):
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1
        return node

    def visit_FunctionDef(self, node):
        if self._depth > 0:
            self.generic_visit(node)
            return node
        if node.name not in self.user_func_set:
            self._depth += 1
            self.generic_visit(node)
            self._depth -= 1
            return node

        # Visit children first so recursive _ft[key] refs are already in place
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

        key = self.key_for[node.name]
        # Unique temp name for the function (not exposed to callers)
        temp_name = (
            "l"
            + hashlib.sha256(f"uf_tmp:{self.salt}:{node.name}".encode()).hexdigest()[:14]
        )
        node.name = temp_name

        # _ft[key] = temp_name
        assign = ast.Assign(
            targets=[
                ast.Subscript(
                    value=ast.Name(id=self.table_varname, ctx=ast.Load()),
                    slice=ast.Constant(value=key),
                    ctx=ast.Store(),
                )
            ],
            value=ast.Name(id=temp_name, ctx=ast.Load()),
            lineno=node.lineno,
            col_offset=node.col_offset,
        )
        # del temp_name
        delete = ast.Delete(
            targets=[ast.Name(id=temp_name, ctx=ast.Del())],
            lineno=node.lineno,
            col_offset=node.col_offset,
        )
        return [node, assign, delete]

    visit_AsyncFunctionDef = visit_FunctionDef


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def obfuscate_source_ast(source: str, filename: str):
    """Obfuscate source at the AST level.

    Returns (obf_source_str, ft_varname, ft_key_map, cv_varname, const_key_map).
    Neither the _ft nor the _c table is inserted into the AST — both live in
    Stage 2 so the code object's dis output has no readable constants or names.
    """
    tree = ast.parse(source, filename=filename)
    rng = make_rng(filename)
    file_salt = hashlib.sha256(f"byepy-r8:{filename}".encode()).hexdigest()[:20]
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
    # Round 11: wrap function bodies in try/except BaseException: raise.
    # Applied after CFF so CFF state machines sit inside the try block.
    # Applied before BuiltinDispatcher so 'BaseException' gets routed through _ft.
    tree = TryExceptWrapper().visit(tree)
    ast.fix_missing_locations(tree)
    # Round 12: inject closure-capturing inner functions at every return point.
    # Applied after TryExceptWrapper so the return lives inside the try body.
    # scrub_code() will garble co_cellvars and co_freevars independently,
    # making the decompiler reference an undefined name in the inner function.
    tree = ClosureCaptureTransformer(rng).visit(tree)
    ast.fix_missing_locations(tree)
    # String encoding with per-position varying key
    tree = XorStringEncoder(xor_key).visit(tree)
    ast.fix_missing_locations(tree)

    # Route ALL builtins AND user-defined top-level functions through _ft[N].
    # The table varname is derived from the file salt so it's different per file.
    ft_varname = scramble_name("_ft", file_salt) or "_ft"

    # Determine which scrambled names map to user-defined functions (for trampolining).
    # We extend _DISPATCH_TARGETS temporarily for the builtin dispatcher to also
    # handle user functions — or we handle them in UserFunctionTrampoline below.
    # Strategy: let BuiltinDispatcher handle true builtins; a separate step
    # handles user functions using the same _ft table.
    user_func_scrambled = set(global_map.values())  # all scrambled user func names

    # Build user-function key map: scrambled_name -> int key (via original name)
    reverse_global = {v: k for k, v in global_map.items()}
    uf_key_for = {
        sc: int(hashlib.sha256(f"ft_idx:{file_salt}:{reverse_global[sc]}".encode()).hexdigest()[:4], 16)
        for sc in user_func_scrambled
    }

    # BuiltinDispatcher handles builtins; we also need user functions in _ft.
    # Use a subclass that adds user-function names to the dispatch target set
    # and overrides _key_for to use pre-computed keys for them.
    _uf_key_for = uf_key_for  # closure capture

    class _FullDispatcher(BuiltinDispatcher):
        def _key_for(self, name: str) -> int:
            if name in _uf_key_for:
                return _uf_key_for[name]
            return super()._key_for(name)

        def visit_Name(self, node):
            if self._in_annotation:
                return node
            if isinstance(node.ctx, ast.Load):
                if node.id in _DISPATCH_TARGETS or node.id in _uf_key_for:
                    return ast.copy_location(self._dispatch_ref(node.id), node)
            return node

    dispatcher = _FullDispatcher(salt=file_salt, table_varname=ft_varname)
    tree = dispatcher.visit(tree)
    ast.fix_missing_locations(tree)

    # Replace function definitions with trampoline stubs (def _tmp; _ft[k]=_tmp; del _tmp)
    tree = UserFunctionTrampoline(
        salt=file_salt,
        table_varname=ft_varname,
        user_func_set=user_func_scrambled,
        key_for=uf_key_for,
    ).visit(tree)
    ast.fix_missing_locations(tree)

    # Build the builtin-only key map for Stage 2 (user functions go via trampolines).
    # User function entries in _ft are populated by the code object itself.
    ft_key_map = {}
    for name in dispatcher.names_used:
        if name in _DISPATCH_TARGETS:
            ft_key_map[name] = int(
                hashlib.sha256(f"ft_idx:{file_salt}:{name}".encode()).hexdigest()[:4], 16
            )
        # user-function names in names_used are scrambled; Stage 2 doesn't need them

    # Integer constant table: collect meaningful ints AFTER all transforms.
    # (String encoder and CFF may have introduced new integer constants.)
    meaningful_ints = collect_meaningful_ints(tree)
    cv_varname = scramble_name("_c", file_salt) or "_c"
    const_key_map = {
        val: int(hashlib.sha256(f"c_idx:{file_salt}:{val}".encode()).hexdigest()[:4], 16)
        for val in meaningful_ints
    }
    tree = ConstantTableizer(cv_varname, const_key_map).visit(tree)
    ast.fix_missing_locations(tree)

    return ast.unparse(tree), ft_varname, ft_key_map, cv_varname, const_key_map


def _encode_builtin_name_s2(name: str, salt: str) -> str:
    """Encode a builtin name for the Stage 2 dispatch table using hex + varying XOR.

    Uses a different encoding scheme from the AST string encoder so one tool
    can't decode both. Key for position i = (K + i*11 + 5) & 0xFF.
    """
    K = int(hashlib.sha256(f"s2_ft:{salt}:{name}".encode()).hexdigest()[:2], 16)
    raw = name.encode("utf-8")
    enc = bytes((b ^ ((K + i * 11 + 5) & 0xFF)) for i, b in enumerate(raw))
    return f"bytes((_b^(({K}+_i*11+5)&255) for _i,_b in enumerate(bytes.fromhex({enc.hex()!r}))).decode()"


def _make_stage2(obf_source: str, file_salt: str,
                 ft_varname: str, ft_key_map: dict,
                 cv_varname: str, const_key_map: dict) -> str:
    """Build Stage 2 bootstrap source: lzma + ctypes + _ft and _c table injection.

    Round 10 changes vs round 9:
    - Code object XOR is position-dependent: key[i%16] ^ ((i>>4)&0xFF) so the
      static extractor's simple b^key[i%16] formula no longer decrypts correctly.
    - _ft table is built via a loop over a list of (key, K, hex) triples instead of
      individual _ft[k]=getattr(...) assignments, breaking extract.py pattern matching.
    - _c table is built via a loop over masked pairs: stored as (key, val^MASK) and
      unmasked at runtime, so extract.py's ast.literal_eval on individual RHS fails.
    """
    code_obj = compile(obf_source, "<generated>", "exec")
    code_obj = scrub_code(code_obj, file_salt)
    raw = lzma.compress(marshal.dumps(code_obj), preset=9)
    key2 = hashlib.sha256(f"s2:{file_salt}".encode()).digest()[:16]
    # Position-dependent XOR: byte i XORed with key2[i%16] ^ ((i>>4)&0xFF)
    enc2 = bytes(b ^ key2[i % 16] ^ ((i >> 4) & 0xFF) for i, b in enumerate(raw))

    # Build _ft for builtins via a loop over (key_int, K_val, enc_hex) triples.
    # The triple list name is a short scrambled alias so it differs from _ft.
    # User functions self-register via trampolines in the code object at exec time.
    if ft_key_map:
        fp_varname = scramble_name("_fp", file_salt) or "_fp"
        triples = []
        for name, key_int in sorted(ft_key_map.items(), key=lambda x: x[1]):
            K = int(hashlib.sha256(f"s2_ft:{file_salt}:{name}".encode()).hexdigest()[:2], 16)
            raw_name = name.encode("utf-8")
            enc_name = bytes((b ^ ((K + i * 11 + 5) & 0xFF)) for i, b in enumerate(raw_name))
            triples.append(f"({key_int},{K},{enc_name.hex()!r})")
        triples_src = ",".join(triples)
        table_src = (
            f"{fp_varname}=[{triples_src}]\n"
            f"{ft_varname}={{}}\n"
            f"for _fk,_fK,_fv in {fp_varname}:\n"
            f"    {ft_varname}[_fk]=getattr(__import__('builtins'),"
            f"bytes(_fb^((_fK+_fi*11+5)&255)"
            f"for _fi,_fb in enumerate(bytes.fromhex(_fv))).decode())\n"
            f"del {fp_varname},_fk,_fK,_fv\n"
        )
    else:
        table_src = ""

    # Build _c constant table via a loop over (key, masked_val) pairs.
    # Values are stored XOR'd with a per-file mask so direct literal extraction fails.
    if const_key_map:
        c_mask = int(hashlib.sha256(f"cv_mask:{file_salt}".encode()).hexdigest()[:4], 16)
        cp_varname = scramble_name("_cp", file_salt) or "_cp"
        pairs = []
        for val, ckey in sorted(const_key_map.items(), key=lambda x: x[1]):
            # Store val XOR'd with mask; unmasked at runtime.  val may be negative
            # so use Python's unlimited ints — mask is always positive 16-bit.
            masked = val ^ c_mask
            pairs.append(f"({ckey},{masked!r})")
        pairs_src = ",".join(pairs)
        c_src = (
            f"_cm={c_mask!r}\n"
            f"{cp_varname}=[{pairs_src}]\n"
            f"{cv_varname}={{}}\n"
            f"for _ck,_cv in {cp_varname}:\n"
            f"    {cv_varname}[_ck]=_cv^_cm\n"
            f"del _cm,{cp_varname},_ck,_cv\n"
        )
    else:
        c_src = ""

    # Exec the code object with _ft, _c, and builtins injected as globals.
    has_tables = bool(ft_key_map or const_key_map)
    if has_tables:
        globals_dict = (
            f"{{'__builtins__':__import__('builtins')"
            + (f",'{ft_varname}':{ft_varname}" if ft_key_map else "")
            + (f",'{cv_varname}':{cv_varname}" if const_key_map else "")
            + f",'__name__':'__main__','__file__':'<generated>'}}"
        )
        exec_line = f"getattr(__import__('builtins'),'exec')(_code,{globals_dict})\n"
    else:
        exec_line = "getattr(__import__('builtins'),'exec')(_code)\n"

    return (
        f"import ctypes as _C,lzma as _L,sys as _s\n"
        f"if _s.gettrace() is not None or _s.getprofile() is not None:raise SystemExit(1)\n"
        f"_api=_C.pythonapi\n"
        f"_api.PyMarshal_ReadObjectFromString.restype=_C.py_object\n"
        f"_api.PyMarshal_ReadObjectFromString.argtypes=[_C.c_char_p,_C.c_ssize_t]\n"
        f"_D2={enc2!r}\n"
        f"_K2={key2!r}\n"
        # Position-dependent XOR: extra (i>>4)&255 term breaks the simple b^key[i%16] extractor
        f"_raw=_L.decompress(bytes(_b^_K2[_i%16]^((_i>>4)&255)for _i,_b in enumerate(_D2)))\n"
        f"_code=_api.PyMarshal_ReadObjectFromString(_raw,len(_raw))\n"
        f"del _D2,_K2,_raw,_api\n"
        f"{table_src}"
        f"{c_src}"
        f"{exec_line}"
    )


def make_bootstrap(src_path: Path, obf_source: str, file_salt: str,
                   ft_varname: str = "", ft_key_map: dict = None,
                   cv_varname: str = "", const_key_map: dict = None) -> str:
    """Two-stage bootstrap: Stage 1 (zlib, type-check) -> Stage 2 (lzma, ctypes) -> code.

    Round 11 change: Stage 2 is now stored as a pre-compiled code object (marshal.dumps)
    rather than a UTF-8 source string.  Stage 1 uses marshal.loads instead of .decode(),
    so extract.py's stage1_decode cannot call .decode() on the payload bytes.
    The agent must decompile Stage 2's code object before extracting _ft and _c.
    """
    stage2_src = _make_stage2(
        obf_source, file_salt,
        ft_varname, ft_key_map or {},
        cv_varname, const_key_map or {},
    )
    # Round 11: compile Stage 2 source → code object, then marshal it.
    stage2_code = compile(stage2_src, "<s2>", "exec")
    stage2_bytes = marshal.dumps(stage2_code)
    raw1 = zlib.compress(stage2_bytes, level=9)
    key1 = hashlib.sha256(f"s1:{file_salt}".encode()).digest()[:16]
    # Round 12: position-dependent Stage 1 XOR adds (i*7+13)&255 twist.
    enc1 = bytes(b ^ key1[i % 16] ^ ((i * 7 + 13) & 255) for i, b in enumerate(raw1))
    return (
        f"import zlib as _Z,sys as _s\n"
        f"if _s.gettrace() is not None or _s.getprofile() is not None:raise SystemExit(1)\n"
        f"if type(_Z.decompress).__name__!='builtin_function_or_method':raise SystemExit(1)\n"
        f"_D={enc1!r}\n"
        f"_K={key1!r}\n"
        # Round 12: marshal.loads + position-dependent Stage 1 decryption.
        f"_src=__import__('marshal').loads(_Z.decompress(bytes(_b^_K[_i%16]^((_i*7+13)&255)for _i,_b in enumerate(_D))))\n"
        f"del _D,_K\n"
        f"getattr(__import__('builtins'),'exec')(_src)\n"
    )


def obfuscate_file_bootstrap(src: Path, dst: Path) -> None:
    source = src.read_text(encoding="utf-8")
    file_salt = hashlib.sha256(f"byepy-r8:{src.name}".encode()).hexdigest()[:20]
    obf_source, ft_varname, ft_key_map, cv_varname, const_key_map = obfuscate_source_ast(
        source, src.name
    )
    bootstrap = make_bootstrap(
        src, obf_source, file_salt,
        ft_varname, ft_key_map,
        cv_varname, const_key_map,
    )
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
    file_salt = hashlib.sha256(f"byepy-r8:{src_dir.name}".encode()).hexdigest()[:20]
    obf_source, ft_varname, ft_key_map, cv_varname, const_key_map = obfuscate_source_ast(
        combined, src_dir.name
    )
    bootstrap = make_bootstrap(
        src_dir, obf_source, file_salt,
        ft_varname, ft_key_map,
        cv_varname, const_key_map,
    )

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
