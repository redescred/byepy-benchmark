"""AST cleanup pass that undoes the obfuscator's transformations on a decompiled module.

Steps:
1. Substitute _ft[N] -> builtin_name (using extracted ft table)
2. Substitute _c[N] -> int literal (using extracted c table)
3. Decode XOR-encoded strings:
     bytes(_b ^ ((K + _i*7 + 3) & 0xFF) for _i,_b in enumerate(bytes.fromhex('hex'))).decode()
4. Remove dead-code If blocks (those whose tests are always False)
5. Collapse CFF (while True: if state == 12: ...; elif state == 7: ...) back to linear code
6. Rename obfuscated identifiers to readable names
7. Remove trampoline registrations: del tmp_name; _ft[k] = tmp_name etc.
"""
import ast
import copy


# ---------------------------------------------------------------------------
# Substitute table lookups
# ---------------------------------------------------------------------------

class TableSubstitutor(ast.NodeTransformer):
    """Replace _ft[N] with Name(builtin_name) and _c[N] with the int literal.

    Also collapses _ft[_c[N]] (double lookup) to the builtin name in one step.
    """
    def __init__(self, ft_varname, ft_table, cv_varname, c_table):
        self.ft = ft_varname
        self.ft_table = ft_table
        self.cv = cv_varname
        self.c_table = c_table

    def visit_Subscript(self, node):
        # Recursively visit children first
        node.value = self.visit(node.value)
        node.slice = self.visit(node.slice)

        # Match: <self.ft>[ <slice> ]   where slice resolves to an int known in ft_table
        if (isinstance(node.value, ast.Name)
                and node.value.id == self.ft):
            key = _resolve_int(node.slice, self.c_table, self.cv)
            if key is not None and key in self.ft_table:
                return ast.Name(id=self.ft_table[key], ctx=node.ctx)

        # Match: <self.cv>[ <slice> ]
        if (isinstance(node.value, ast.Name)
                and node.value.id == self.cv):
            key = _resolve_int(node.slice, self.c_table, self.cv)
            if key is not None and key in self.c_table:
                return ast.Constant(value=self.c_table[key])

        return node


def _resolve_int(node, c_table, cv_name):
    """Try to resolve an AST expression to an int constant. Handles:
       - ast.Constant int
       - _c[int_const]  (so _c lookups that haven't been substituted yet)
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if (isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == cv_name
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, int)):
        return c_table.get(node.slice.value)
    return None


# ---------------------------------------------------------------------------
# Dead-code removal: drop If blocks whose test is always False
# ---------------------------------------------------------------------------

DEAD_PATTERNS = [
    # ast.Compare with NaN-identity trick: x is not None and x != x
    "naneq",
    # Comparisons against impossible bounds
    "obvious",
    # Round 9: SHA-256 all-zero prefix check
    "sha256_zero",
]


def _is_sha256_dead_test(node):
    """Return True for the round 9 SHA-256 always-False predicate.

    Pattern:
        __import__('hashlib').sha256(str(EXPR).encode()).digest()[None:N] == b'\\x00'*N

    The decompiler represents [:N] as a Slice(lower=None, upper=N) subscript.
    SHA-256 never produces an all-zero output, so this is always False.
    We detect it structurally without executing the hash.
    """
    # Must be a Compare: <lhs> == <bytes_literal>
    if not (isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.Eq)):
        return False

    rhs = node.comparators[0]
    # rhs must be a bytes literal of all zeros
    if not isinstance(rhs, ast.Constant):
        return False
    if not isinstance(rhs.value, bytes):
        return False
    if not rhs.value or any(b != 0 for b in rhs.value):
        return False

    # lhs must be: <something>.digest()[None:N]
    lhs = node.left
    if not (isinstance(lhs, ast.Subscript)):
        return False
    # The subscript slice should be None:N (Slice with lower=None or lower=Constant(None))
    slc = lhs.slice
    if isinstance(slc, ast.Slice):
        # lower is None or ast.Constant(None)
        low_ok = (slc.lower is None
                  or (isinstance(slc.lower, ast.Constant) and slc.lower.value is None))
        if not low_ok:
            return False
    else:
        return False

    # The subscripted value should be a call to .digest()
    digest_call = lhs.value
    if not (isinstance(digest_call, ast.Call)
            and isinstance(digest_call.func, ast.Attribute)
            and digest_call.func.attr == "digest"
            and not digest_call.args
            and not digest_call.keywords):
        return False

    # The .digest() receiver should be sha256(...)
    sha_call = digest_call.func.value
    if not isinstance(sha_call, ast.Call):
        return False
    # sha256 can appear as __import__('hashlib').sha256 or hashlib.sha256
    func = sha_call.func
    if isinstance(func, ast.Attribute) and func.attr == "sha256":
        return True

    return False


def _is_algebraic_dead_test(node):
    """Return True for round-10 algebraic opaque predicates.

    These are always-False comparisons of the form:
        POLY(n) % 2 == 1
    where POLY is a degree-2 polynomial in one variable whose parity is provably
    always even:
        n*(n+1)   -- product of consecutive integers, always even
        n*n - n   -- n*(n-1), same
        n*n + n   -- n*(n+1), same

    The pattern is: Compare( BinOp(POLY, Mod, 2), Eq, 1 )
    """
    # Must be EXPR % 2 == 1  (i.e., the integer 1, making it always False)
    if not (isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.Eq)
            and isinstance(node.comparators[0], ast.Constant)
            and node.comparators[0].value == 1):
        return False

    lhs = node.left
    # lhs must be POLY % 2
    if not (isinstance(lhs, ast.BinOp)
            and isinstance(lhs.op, ast.Mod)
            and isinstance(lhs.right, ast.Constant)
            and lhs.right.value == 2):
        return False

    poly = lhs.left
    # Check that poly is a product of two linear expressions sharing one Name
    # We accept:
    #   n * (n + 1)    BinOp(Mult, Name, BinOp(Add, Name, Const))
    #   n * (n - 1)    BinOp(Mult, Name, BinOp(Sub, Name, Const))
    #   (n + 1) * n    reversed
    #   n * n - n      BinOp(Sub, BinOp(Mult, Name, Name), Name)
    #   n * n + n      BinOp(Add, BinOp(Mult, Name, Name), Name)
    if not isinstance(poly, ast.BinOp):
        return False

    if isinstance(poly.op, ast.Mult):
        # n * (n ± c)
        left, right = poly.left, poly.right
        # Normalise: ensure left is a Name
        if isinstance(right, ast.Name) and isinstance(left, ast.BinOp):
            left, right = right, left
        if not isinstance(left, ast.Name):
            return False
        if isinstance(right, ast.Name) and right.id == left.id:
            # n * n: even only if n is always even -- not provably so; skip
            return False
        if isinstance(right, ast.BinOp) and isinstance(right.op, (ast.Add, ast.Sub)):
            inner_name = right.left if isinstance(right.left, ast.Name) else None
            if inner_name and inner_name.id == left.id:
                return True
        return False

    if isinstance(poly.op, (ast.Add, ast.Sub)):
        # n*n - n  or  n*n + n
        if isinstance(poly.left, ast.BinOp) and isinstance(poly.left.op, ast.Mult):
            mul = poly.left
            if (isinstance(mul.left, ast.Name) and isinstance(mul.right, ast.Name)
                    and mul.left.id == mul.right.id):
                # n*n +/- n: always even (n*(n +/- 1))
                if isinstance(poly.right, ast.Name) and poly.right.id == mul.left.id:
                    return True
        return False

    return False


def _is_isinstance_dead_test(node):
    """Return True for isinstance(LITERAL, TYPE) calls that are provably always False.

    Round 11 uses these as opaque dead-code predicates: isinstance(0, float),
    isinstance(True, str), isinstance([], dict), isinstance('', int), etc.
    After TableSubstitutor substitution they appear as isinstance(LITERAL, BUILTIN_NAME).
    """
    if not (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) == 2
            and not node.keywords):
        return False
    value_node, type_node = node.args
    if not isinstance(type_node, ast.Name):
        return False
    type_name = type_node.id
    TYPE_MAP = {
        "int": int, "float": float, "str": str, "bytes": bytes,
        "bool": bool, "list": list, "dict": dict, "tuple": tuple,
        "set": set, "type": type, "complex": complex,
    }
    if type_name not in TYPE_MAP:
        return False
    # value_node must be a constant we can introspect
    if not isinstance(value_node, ast.Constant):
        # Also handle ast.List([]), ast.Dict(), ast.Tuple() as literal containers
        if isinstance(value_node, ast.List):
            val = list
        elif isinstance(value_node, ast.Dict):
            val = dict
        elif isinstance(value_node, ast.Tuple):
            val = tuple
        elif isinstance(value_node, ast.Set):
            val = set
        else:
            return False
        expected_type = TYPE_MAP[type_name]
        return val is not expected_type
    val = value_node.value
    expected_type = TYPE_MAP[type_name]
    return not isinstance(val, expected_type)


def _is_sys_dead_test(node):
    """Return True for sys-module invariant comparisons that are always False on Python 3 64-bit.

    Patterns detected:
        __import__('sys').maxsize < 0
        __import__('sys').version_info < (1, 0)
        __import__('sys').version_info > (99, 0)
        __import__('sys').float_info.max < 0
    """
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1:
        return False

    lhs = node.left
    op = node.ops[0]
    rhs = node.comparators[0]

    def _is_sys_import(n):
        if isinstance(n, ast.Name) and n.id == "sys":
            return True
        if (isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "__import__"
                and len(n.args) == 1
                and isinstance(n.args[0], ast.Constant)
                and n.args[0].value == "sys"):
            return True
        return False

    def _is_sys_attr(n, attr):
        return (isinstance(n, ast.Attribute)
                and n.attr == attr
                and _is_sys_import(n.value))

    def _int_const(n, val):
        return isinstance(n, ast.Constant) and n.value == val

    def _tuple_first_le(n, bound):
        # Handle both ast.Tuple([Constant(1), Constant(0)]) and ast.Constant((1, 0))
        if isinstance(n, ast.Tuple) and n.elts:
            first = n.elts[0]
            return isinstance(first, ast.Constant) and first.value <= bound
        if isinstance(n, ast.Constant) and isinstance(n.value, tuple) and n.value:
            return n.value[0] <= bound
        return False

    def _tuple_first_ge(n, bound):
        if isinstance(n, ast.Tuple) and n.elts:
            first = n.elts[0]
            return isinstance(first, ast.Constant) and first.value >= bound
        if isinstance(n, ast.Constant) and isinstance(n.value, tuple) and n.value:
            return n.value[0] >= bound
        return False

    if _is_sys_attr(lhs, "maxsize") and isinstance(op, ast.Lt) and _int_const(rhs, 0):
        return True
    if _is_sys_attr(lhs, "version_info") and isinstance(op, ast.Lt) and _tuple_first_le(rhs, 1):
        return True
    if _is_sys_attr(lhs, "version_info") and isinstance(op, ast.Gt) and _tuple_first_ge(rhs, 99):
        return True
    if (isinstance(lhs, ast.Attribute) and lhs.attr == "max"
            and isinstance(lhs.value, ast.Attribute) and lhs.value.attr == "float_info"
            and _is_sys_import(lhs.value.value)
            and isinstance(op, ast.Lt) and _int_const(rhs, 0)):
        return True
    return False



def _is_banker_rounding_dead_test(node):
    """Round 13: round(N.5) != N predicates are always False (banker rounding)."""
    if not (isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.NotEq)):
        return False
    lhs = node.left
    rhs = node.comparators[0]
    if not (isinstance(lhs, ast.Call)
            and isinstance(lhs.func, ast.Name)
            and lhs.func.id == "round"
            and len(lhs.args) == 1
            and not lhs.keywords):
        return False
    arg = lhs.args[0]
    if not isinstance(arg, ast.Constant):
        return False
    val = arg.value
    if not isinstance(val, float):
        return False
    frac = val - int(val)
    if abs(frac - 0.5) > 1e-9:
        return False
    if not isinstance(rhs, ast.Constant):
        return False
    if rhs.value != round(val):
        return False
    return True


def _is_abs_divmod_dead_test(node):
    """Round 13: abs(-N) > N  and  divmod(A,B)[0] != A//B  are always False."""
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1:
        return False
    lhs = node.left
    op = node.ops[0]
    rhs = node.comparators[0]
    # abs(-N) > N
    if isinstance(op, ast.Gt):
        if (isinstance(lhs, ast.Call)
                and isinstance(lhs.func, ast.Name)
                and lhs.func.id == "abs"
                and len(lhs.args) == 1
                and not lhs.keywords):
            arg = lhs.args[0]
            if isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                inner = arg.operand
                if (isinstance(inner, ast.Constant)
                        and isinstance(inner.value, int)
                        and inner.value > 0
                        and isinstance(rhs, ast.Constant)
                        and rhs.value == inner.value):
                    return True
    # divmod(A, B)[0] != A//B
    if isinstance(op, ast.NotEq):
        if (isinstance(lhs, ast.Subscript)
                and isinstance(lhs.value, ast.Call)
                and isinstance(lhs.value.func, ast.Name)
                and lhs.value.func.id == "divmod"
                and len(lhs.value.args) == 2
                and not lhs.value.keywords
                and isinstance(lhs.slice, ast.Constant)
                and lhs.slice.value == 0):
            try:
                a = ast.literal_eval(lhs.value.args[0])
                b = ast.literal_eval(lhs.value.args[1])
                expected = a // b
                rhs_val = ast.literal_eval(rhs)
                if rhs_val == expected:
                    return True
            except Exception:
                pass
    return False


def _is_chr_ord_dead_test(node):
    """Round 13: ord(chr(N)) != N  and  chr(N) != chr(N)  are always False."""
    if not (isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.NotEq)):
        return False
    lhs = node.left
    rhs = node.comparators[0]
    # ord(chr(N)) != N
    if (isinstance(lhs, ast.Call)
            and isinstance(lhs.func, ast.Name)
            and lhs.func.id == "ord"
            and len(lhs.args) == 1
            and not lhs.keywords):
        inner = lhs.args[0]
        if (isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "chr"
                and len(inner.args) == 1
                and not inner.keywords
                and isinstance(inner.args[0], ast.Constant)
                and isinstance(inner.args[0].value, int)):
            n = inner.args[0].value
            if isinstance(rhs, ast.Constant) and rhs.value == n:
                return True
    # chr(N) != chr(N)
    if (isinstance(lhs, ast.Call)
            and isinstance(rhs, ast.Call)
            and isinstance(lhs.func, ast.Name) and lhs.func.id == "chr"
            and isinstance(rhs.func, ast.Name) and rhs.func.id == "chr"
            and len(lhs.args) == 1 and len(rhs.args) == 1
            and not lhs.keywords and not rhs.keywords):
        try:
            lv = ast.literal_eval(lhs.args[0])
            rv = ast.literal_eval(rhs.args[0])
            if lv == rv:
                return True
        except Exception:
            pass
    return False


def _is_int_construction_dead_test(node):
    """Round 13: int(True)!=1, int(False)!=0, bool(0) is not False, etc. always False."""
    if not (isinstance(node, ast.Compare)
            and len(node.ops) == 1):
        return False
    lhs = node.left
    op = node.ops[0]
    rhs = node.comparators[0]
    if isinstance(op, ast.NotEq):
        if (isinstance(lhs, ast.Call)
                and isinstance(lhs.func, ast.Name)
                and lhs.func.id in ("int", "bool")
                and len(lhs.args) == 1
                and not lhs.keywords
                and isinstance(lhs.args[0], ast.Constant)):
            fn_name = lhs.func.id
            arg_val = lhs.args[0].value
            try:
                expected = int(arg_val) if fn_name == "int" else bool(arg_val)
            except Exception:
                return False
            if isinstance(rhs, ast.Constant) and rhs.value == expected:
                return True
    if isinstance(op, ast.IsNot):
        if (isinstance(lhs, ast.Call)
                and isinstance(lhs.func, ast.Name)
                and lhs.func.id == "bool"
                and len(lhs.args) == 1
                and not lhs.keywords
                and isinstance(lhs.args[0], ast.Constant)):
            arg_val = lhs.args[0].value
            try:
                expected = bool(arg_val)
            except Exception:
                return False
            if isinstance(rhs, ast.Constant) and rhs.value is expected:
                return True
    return False


def _is_dead_test(node):
    """Return True for predicates we recognise as always-False."""
    # `False`
    if isinstance(node, ast.Constant) and node.value is False:
        return True
    # `None is not None`
    if (isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.IsNot)
            and isinstance(node.left, ast.Constant) and node.left.value is None
            and isinstance(node.comparators[0], ast.Constant)
            and node.comparators[0].value is None):
        return True
    # NaN-identity composite: x is not None and x != x
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        if any(_is_self_neq(v) for v in node.values):
            return True
    if _is_self_neq(node):
        return True
    # Round 9: SHA-256 all-zero prefix
    if _is_sha256_dead_test(node):
        return True
    # Round 10: algebraic opaque predicates
    if _is_algebraic_dead_test(node):
        return True
    # Round 11: isinstance(LITERAL, TYPE) always-False predicates
    if _is_isinstance_dead_test(node):
        return True
    # Round 11: sys-module invariant always-False predicates
    if _is_sys_dead_test(node):
        return True
    # Round 13: banker rounding  round(N.5) != N
    if _is_banker_rounding_dead_test(node):
        return True
    # Round 13: abs(-N) > N  and  divmod(A,B)[0] != A//B
    if _is_abs_divmod_dead_test(node):
        return True
    # Round 13: ord(chr(N)) != N  and  chr(N) != chr(N)
    if _is_chr_ord_dead_test(node):
        return True
    # Round 13: int(True)!=1, int(False)!=0, bool(0) is not False
    if _is_int_construction_dead_test(node):
        return True
    return False


def _is_self_neq(node):
    """Is this `x != x`?"""
    if (isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.NotEq)
            and isinstance(node.left, ast.Name)
            and isinstance(node.comparators[0], ast.Name)
            and node.left.id == node.comparators[0].id):
        return True
    return False


def _matches_nan_id_check(node):
    """Recognize the nested form:
        if x is not None:
            if x != x:
                return x
    Return True if this is the dead-code NaN-identity check.
    """
    if not isinstance(node, ast.If):
        return False
    if not (isinstance(node.test, ast.Compare)
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.IsNot)
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value is None
            and isinstance(node.test.left, ast.Name)):
        return False
    var_name = node.test.left.id
    if len(node.body) != 1 or not isinstance(node.body[0], ast.If):
        return False
    inner = node.body[0]
    if not _is_self_neq(inner.test):
        return False
    if not all(isinstance(s, (ast.Return, ast.Pass)) for s in inner.body):
        return False
    return True


def _dead_body_only(body):
    """Return True if every statement in body is a dead-code-only kind:
    assignments, raises, returns, or passes — with no else branch and no
    real side effects.  Round 9 dead bodies are 2-4 such statements.
    """
    if not body:
        return False
    for s in body:
        if isinstance(s, (ast.Return, ast.Raise, ast.Pass)):
            continue
        if isinstance(s, ast.Assign):
            continue
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
            continue
        return False
    return True


def _has_real_raise(body):
    """Return True if the body has a `raise ExceptionType(...)` — likely real user code."""
    for s in body:
        if (isinstance(s, ast.Raise)
                and s.exc is not None
                and not (isinstance(s.exc, ast.Constant) and s.exc.value is None)):
            return True
    return False


def _matches_other_dead_check(node):
    """Recognize:
        if x < 0:            <dead body>
        if x > NNN:          <dead body>
        if len(v) > NNN:     <dead body>
    Bodies may now be 1-4 statements (round 9 raised this from 1).

    Note: `if x < 0:` is excluded from dead-code removal if the body contains
    a real raise (e.g., `raise ValueError('...')`), since that is likely a
    legitimate input-validation guard from the original source.
    """
    if not isinstance(node, ast.If):
        return False
    if node.orelse:
        return False

    test = node.test
    # `if x < <small_int>:` where <small_int> is <= 0
    # Guard: skip if body contains a real raise (legitimate user code)
    if (isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Lt)
            and isinstance(test.comparators[0], ast.Constant)
            and isinstance(test.comparators[0].value, int)
            and test.comparators[0].value <= 0):
        if _dead_body_only(node.body) and not _has_real_raise(node.body):
            return True

    # `if x > <large_int>:` dead body
    if (isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Gt)
            and isinstance(test.comparators[0], ast.Constant)
            and isinstance(test.comparators[0].value, int)
            and test.comparators[0].value >= 200):
        if _dead_body_only(node.body):
            return True

    # `if len(<name>) > NNN:` dead body
    if (isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Gt)
            and isinstance(test.left, ast.Call)
            and isinstance(test.left.func, ast.Name)
            and test.left.func.id == "len"
            and isinstance(test.comparators[0], ast.Constant)
            and isinstance(test.comparators[0].value, int)
            and test.comparators[0].value >= 100):
        if _dead_body_only(node.body):
            return True

    return False


class DeadCodeRemover(ast.NodeTransformer):
    def visit_If(self, node):
        # Recurse first
        node = self.generic_visit(node)
        node.body = _flatten(node.body)
        node.orelse = _flatten(node.orelse)
        # Strip trailing `return None` from if-true branch when there's no else
        if (not node.orelse and node.body
                and isinstance(node.body[-1], ast.Return)
                and isinstance(node.body[-1].value, ast.Constant)
                and node.body[-1].value.value is None):
            node.body.pop()
        if _is_dead_test(node.test):
            # Replace with its orelse only (or remove if no else)
            return node.orelse if node.orelse else []
        if _matches_nan_id_check(node):
            return []
        if _matches_other_dead_check(node):
            return []
        # Outer if whose body became empty after dead-code removal => drop it
        if not node.body and not node.orelse:
            return []
        # Outer if where the body collapsed to a no-op (just the nested dead check) =>
        # the whole if becomes dead
        if (len(node.body) == 1 and isinstance(node.body[0], ast.If)
                and _matches_nan_id_check(node.body[0])):
            return []
        if not node.body:
            node.body = [ast.Pass()]
        return node

    def visit_FunctionDef(self, node):
        node = self.generic_visit(node)
        node.body = _flatten(node.body)
        if not node.body:
            node.body = [ast.Pass()]
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_For(self, node):
        node = self.generic_visit(node)
        node.body = _flatten(node.body)
        if not node.body:
            node.body = [ast.Pass()]
        return node

    def visit_While(self, node):
        node = self.generic_visit(node)
        node.body = _flatten(node.body)
        if not node.body:
            node.body = [ast.Pass()]
        return node

    def visit_Module(self, node):
        node = self.generic_visit(node)
        node.body = _flatten(node.body)
        return node

    def visit_ClassDef(self, node):
        node = self.generic_visit(node)
        node.body = _flatten(node.body)
        if not node.body:
            node.body = [ast.Pass()]
        return node


def _flatten(stmts):
    out = []
    for s in stmts:
        if isinstance(s, list):
            out.extend(s)
        elif s is None:
            continue
        else:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# CFF (control-flow flattening) reversal
# ---------------------------------------------------------------------------

class CFFUnflatten(ast.NodeTransformer):
    """Recognize the obfuscator's state-machine pattern and linearize it.

    Pattern (in a function body):
        <sv> = <initial_state_int>
        while True:
            if <sv> == <state_a>:
                <body_a>; <sv> = <state_b>
            elif <sv> == <state_b>:
                <body_b>; <sv> = <state_c>
            ...
            elif <sv> == <state_n>:
                <body_n>; <rv> = <expr>; break    # or just break
            else:
                pass
        return <rv>   (optional; only if a `<rv> = expr; break` case existed)
    """

    def visit_FunctionDef(self, node):
        node = self.generic_visit(node)
        node.body = self._unflatten(node.body)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Module(self, node):
        node = self.generic_visit(node)
        node.body = self._unflatten(node.body)
        return node

    def _unflatten(self, stmts):
        # Look for the (sv = const) then (while True: ...) (then return rv?) pattern
        # We scan windows of 2-3 statements
        i = 0
        new = []
        while i < len(stmts):
            s = stmts[i]
            if (isinstance(s, ast.Assign)
                    and len(s.targets) == 1
                    and isinstance(s.targets[0], ast.Name)
                    and isinstance(s.value, ast.Constant)
                    and isinstance(s.value.value, int)
                    and i + 1 < len(stmts)
                    and isinstance(stmts[i+1], ast.While)
                    and _is_true_const(stmts[i+1].test)):
                sv_name = s.targets[0].id
                initial_state = s.value.value
                while_node = stmts[i+1]
                # parse the chain of elifs inside the while
                state_map = _extract_state_map(while_node.body, sv_name)
                if state_map is not None:
                    # Look-ahead for optional `return rv` after the while
                    return_node = None
                    if i + 2 < len(stmts) and isinstance(stmts[i+2], ast.Return):
                        return_node = stmts[i+2]

                    seq = _linearize(state_map, initial_state, sv_name,
                                     return_node)
                    if seq is not None:
                        new.extend(seq)
                        i += 3 if return_node is not None else 2
                        continue
            new.append(s)
            i += 1
        return new


def _is_true_const(node):
    return isinstance(node, ast.Constant) and node.value is True


def _extract_state_map(while_body, sv_name):
    """Parse the cascading `if/elif` inside the while True body.

    Returns dict {state_int: (body_stmts_minus_terminator, next_state_int_or_break_info)}
    or None if the pattern doesn't match cleanly.
    """
    if len(while_body) != 1:
        return None
    chain = while_body[0]
    state_map = {}
    while isinstance(chain, ast.If):
        # Recognize the test: <sv> == <int>
        t = chain.test
        if not (isinstance(t, ast.Compare)
                and len(t.ops) == 1
                and isinstance(t.ops[0], ast.Eq)
                and isinstance(t.left, ast.Name)
                and t.left.id == sv_name
                and isinstance(t.comparators[0], ast.Constant)
                and isinstance(t.comparators[0].value, int)):
            return None
        state = t.comparators[0].value

        # Inspect tail of body for the terminator
        body = list(chain.body)
        terminator = _strip_terminator(body, sv_name)
        if terminator is None:
            return None
        state_map[state] = (body, terminator)

        # Continue with orelse
        if not chain.orelse:
            break
        if len(chain.orelse) == 1 and isinstance(chain.orelse[0], ast.If):
            chain = chain.orelse[0]
            continue
        # if orelse is [Pass()] we're done
        if len(chain.orelse) == 1 and isinstance(chain.orelse[0], ast.Pass):
            break
        # Unknown tail
        return None

    return state_map


def _strip_terminator(body, sv_name):
    """Pull off the final statement(s) that determine next-state/break.

    Returns one of:
        ("next", state_int)  if the case ends with `sv = <int>`
        ("break", None)      if the case ends with bare `break`
        ("ret_break", expr)  if the case ends with `rv = expr; break`
    Mutates `body` to remove the terminator.
    """
    if not body:
        return None

    last = body[-1]
    # Bare break
    if isinstance(last, ast.Break):
        # Could be preceded by `rv = expr`
        if len(body) >= 2 and isinstance(body[-2], ast.Assign) \
                and len(body[-2].targets) == 1 \
                and isinstance(body[-2].targets[0], ast.Name) \
                and body[-2].targets[0].id != sv_name:
            rv_assign = body[-2]
            body.pop()
            body.pop()
            return ("ret_break", rv_assign)
        body.pop()
        return ("break", None)
    # sv = <int>
    if (isinstance(last, ast.Assign)
            and len(last.targets) == 1
            and isinstance(last.targets[0], ast.Name)
            and last.targets[0].id == sv_name
            and isinstance(last.value, ast.Constant)
            and isinstance(last.value.value, int)):
        body.pop()
        return ("next", last.value.value)
    return None


def _linearize(state_map, initial_state, sv_name, return_node):
    """Convert the state map into a linear list of statements.

    return_node, if present, is `return <name>` after the while. The corresponding
    `<name> = expr` assignment is the `rv` set in the (ret_break, ...) terminator.
    """
    seq = []
    current = initial_state
    visited = set()
    rv_var = None
    if return_node is not None and isinstance(return_node.value, ast.Name):
        rv_var = return_node.value.id

    while current in state_map and current not in visited:
        visited.add(current)
        body, term = state_map[current]
        seq.extend(body)
        kind = term[0]
        if kind == "next":
            current = term[1]
            continue
        if kind == "break":
            return seq
        if kind == "ret_break":
            rv_assign = term[1]
            # rv_assign.value is the return value
            seq.append(ast.Return(value=rv_assign.value))
            return seq
    # Loop didn't terminate cleanly; bail
    if current not in state_map:
        # If we have a return_node still pending, append it
        if return_node is not None:
            seq.append(return_node)
        return seq
    return None


# ---------------------------------------------------------------------------
# Scrambled CFF unflatener (round 9 variant)
# ---------------------------------------------------------------------------

class ScrambledCFFUnflatten(ast.NodeTransformer):
    """Handle the round 9 'scrambled' CFF where the state machine is split
    into separate if/elif pairs rather than a single nested if/elif chain.

    Pattern:
        sv = INIT
        while sv == LOOP_STATE:
            <body>
            sv = NEXT
        if sv == A:
            <body_a>
            sv = B
        elif sv == C:
            <body_c>
            sv = D
        if sv == E:
            ...
        ...

    We collect all (state -> body, next_state) from the while body and all
    top-level if/elif chains, then linearize from INIT.
    """

    def visit_FunctionDef(self, node):
        node = self.generic_visit(node)
        node.body = self._unflatten_scrambled(node.body)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Module(self, node):
        node = self.generic_visit(node)
        node.body = self._unflatten_scrambled(node.body)
        return node

    def _unflatten_scrambled(self, stmts):
        """Try to detect and unflatten a scrambled CFF block in stmts."""
        i = 0
        new = []
        while i < len(stmts):
            s = stmts[i]
            # Look for: sv = CONST_INT
            if not (isinstance(s, ast.Assign)
                    and len(s.targets) == 1
                    and isinstance(s.targets[0], ast.Name)
                    and isinstance(s.value, ast.Constant)
                    and isinstance(s.value.value, int)):
                new.append(s)
                i += 1
                continue

            sv_name = s.targets[0].id
            initial_state = s.value.value

            # Scan forward: collect while sv==X: ... and if sv==A: ... elif sv==B: ...
            j = i + 1
            while_state = None
            while_body = None
            if j < len(stmts) and isinstance(stmts[j], ast.While):
                wtest = stmts[j].test
                # while sv == SOME_STATE
                if (isinstance(wtest, ast.Compare)
                        and len(wtest.ops) == 1
                        and isinstance(wtest.ops[0], ast.Eq)
                        and isinstance(wtest.left, ast.Name)
                        and wtest.left.id == sv_name
                        and isinstance(wtest.comparators[0], ast.Constant)
                        and isinstance(wtest.comparators[0].value, int)):
                    while_state = wtest.comparators[0].value
                    while_body = stmts[j].body
                    j += 1

            # Collect all subsequent if/elif blocks that switch on sv
            state_map = {}  # state_int -> (real_body_stmts, next_state_or_term)

            # Add the while body as a state entry
            if while_state is not None and while_body is not None:
                entry = _parse_sv_block(while_body, sv_name)
                if entry is not None:
                    state_map[while_state] = entry

            # Collect if/elif chains
            while j < len(stmts) and isinstance(stmts[j], ast.If):
                chain = stmts[j]
                collected = _collect_elif_chain(chain, sv_name)
                if collected is None:
                    break
                state_map.update(collected)
                j += 1

            # Only proceed if we collected a useful state map
            if len(state_map) < 2 or initial_state not in state_map:
                new.append(s)
                i += 1
                continue

            # Linearize
            seq = _linearize_scrambled(state_map, initial_state, sv_name)
            if seq is None:
                new.append(s)
                i += 1
                continue

            new.extend(seq)
            i = j
        return new


def _parse_sv_block(stmts, sv_name):
    """Parse a block's body: return (real_stmts, terminator) or None.

    Terminator is ("next", state_int) or ("return", value) or ("end", None).
    Strips dead-code SHA-256 checks and sv assignments.
    """
    real = []
    term = ("end", None)
    for stmt in stmts:
        # Skip SHA-256 dead code
        if isinstance(stmt, ast.If) and _is_dead_test(stmt.test) and not stmt.orelse:
            continue
        # sv = NEXT_STATE -> terminator
        if (isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == sv_name
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, int)):
            term = ("next", stmt.value.value)
            continue
        # return statement
        if isinstance(stmt, ast.Return):
            term = ("return", stmt.value)
            continue
        real.append(stmt)
    return (real, term)


def _collect_elif_chain(chain, sv_name):
    """Collect all (state -> (body, term)) from a chain of if/elif that switch on sv_name.

    Also handles `else: if sv==X: ...; if sv==Y: ...` flat blocks (round 9 scrambled CFF).

    Returns dict or None if the chain doesn't match the pattern.
    """
    result = {}
    node = chain
    while isinstance(node, ast.If):
        test = node.test
        if not (isinstance(test, ast.Compare)
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
                and isinstance(test.left, ast.Name)
                and test.left.id == sv_name
                and isinstance(test.comparators[0], ast.Constant)
                and isinstance(test.comparators[0].value, int)):
            return None
        state = test.comparators[0].value
        entry = _parse_sv_block(node.body, sv_name)
        if entry is None:
            return None
        result[state] = entry
        if not node.orelse:
            break
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            node = node.orelse[0]
        elif len(node.orelse) == 1 and isinstance(node.orelse[0], ast.Pass):
            break
        else:
            # Flat else block: could be `if sv==X: ...; if sv==Y: ...`
            # Extract states from each statement in the else block
            for s in node.orelse:
                if isinstance(s, ast.If) and _is_dead_test(s.test):
                    continue
                if isinstance(s, ast.If):
                    sub = _collect_elif_chain(s, sv_name)
                    if sub is not None:
                        result.update(sub)
                    # else: non-state if, skip
            break
    return result if result else None


def _linearize_scrambled(state_map, initial_state, sv_name):
    """Linearize a scrambled CFF state machine."""
    seq = []
    current = initial_state
    visited = set()

    while current in state_map and current not in visited:
        visited.add(current)
        body, term = state_map[current]
        seq.extend(body)
        kind = term[0]
        if kind == "next":
            current = term[1]
        elif kind == "return":
            seq.append(ast.Return(value=term[1]))
            return seq
        elif kind == "end":
            return seq

    # If we ran out of states or hit a cycle with no return
    return seq if seq else None


# ---------------------------------------------------------------------------
# String decoding (XOR + bytes.fromhex)
# ---------------------------------------------------------------------------

class XorStringDecoder(ast.NodeTransformer):
    """Decode strings of the form:

        bytes(_b ^ ((K + _i*7 + 3) & 0xFF) for _i, _b in enumerate(bytes.fromhex(<hex>))).decode()

    or its Stage-2 variant with *11+5 instead of *7+3. The latter shows up in Stage 2 only
    (not in the code object), so for the AST we focus on *7+3.
    """
    def visit_Call(self, node):
        node = self.generic_visit(node)
        s = _try_decode_xor_string(node)
        if s is not None:
            return ast.copy_location(ast.Constant(value=s), node)
        return node


def _try_decode_xor_string(node):
    """If node is a bytes(_b ^ ((K + _i*M + N) & 0xFF) for _i,_b in enumerate(bytes.fromhex(HEX))).decode()
    pattern, return the decoded string. Else return None."""
    # node should be Call(func=Attribute(value=<bytes_call>, attr='decode'), args=[])
    if not isinstance(node, ast.Call):
        return None
    if node.args:
        return None
    if not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != "decode":
        return None
    bytes_call = node.func.value
    if not (isinstance(bytes_call, ast.Call)
            and isinstance(bytes_call.func, ast.Name)
            and bytes_call.func.id == "bytes"
            and len(bytes_call.args) == 1):
        return None
    # The argument is either a GeneratorExp or a CallExpr representing the genexp's __call__
    # but for our decompiler we may have ended up with a Call to a hidden lambda — let's also
    # accept that.
    genexp = bytes_call.args[0]
    if isinstance(genexp, ast.GeneratorExp):
        return _decode_from_genexp(genexp)
    return None


def _decode_from_genexp(genexp: ast.GeneratorExp):
    # elt: <byte_var> ^ ((K + <idx_var>*M + N) & 0xFF)
    elt = genexp.elt
    if not (isinstance(elt, ast.BinOp) and isinstance(elt.op, ast.BitXor)):
        return None

    # iter: enumerate(bytes.fromhex(HEX))
    if len(genexp.generators) != 1:
        return None
    gen = genexp.generators[0]
    if not (isinstance(gen.iter, ast.Call)
            and isinstance(gen.iter.func, ast.Name)
            and gen.iter.func.id == "enumerate"
            and len(gen.iter.args) == 1):
        return None

    # Identify the target tuple (idx_var, byte_var)
    if not isinstance(gen.target, ast.Tuple) or len(gen.target.elts) != 2:
        return None
    idx_var = gen.target.elts[0].id if isinstance(gen.target.elts[0], ast.Name) else None
    byte_var = gen.target.elts[1].id if isinstance(gen.target.elts[1], ast.Name) else None
    if idx_var is None or byte_var is None:
        return None

    # elt.left should be the byte var
    if not (isinstance(elt.left, ast.Name) and elt.left.id == byte_var):
        return None

    key_expr = elt.right
    K, M, N, mod = _extract_K_M_N(key_expr, idx_var)
    if K is None:
        return None

    inner = gen.iter.args[0]
    if not (isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "fromhex"
            and isinstance(inner.func.value, ast.Name)
            and inner.func.value.id == "bytes"
            and len(inner.args) == 1
            and isinstance(inner.args[0], ast.Constant)
            and isinstance(inner.args[0].value, str)):
        return None
    hex_str = inner.args[0].value
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError:
        return None
    out = bytes((b ^ ((K + i * M + N) & mod)) for i, b in enumerate(raw))
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _extract_K_M_N(node, idx_var=None):
    """Walk the expression (K + <idx>*M + N) & MOD and pull out K, M, N, MOD.

    Sample shape:
        BinOp(BitAnd,
            left=BinOp(Add,
                left=BinOp(Add,
                    left=Constant(K),
                    right=BinOp(Mult, left=Name(idx), right=Constant(M))),
                right=Constant(N)),
            right=Constant(MOD))
    """
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitAnd)):
        return None, None, None, None
    if not isinstance(node.right, ast.Constant):
        return None, None, None, None
    MOD = node.right.value

    add2 = node.left
    if not (isinstance(add2, ast.BinOp) and isinstance(add2.op, ast.Add)):
        return None, None, None, None
    if not isinstance(add2.right, ast.Constant):
        return None, None, None, None
    N = add2.right.value

    add1 = add2.left
    if not (isinstance(add1, ast.BinOp) and isinstance(add1.op, ast.Add)):
        return None, None, None, None
    if not isinstance(add1.left, ast.Constant):
        return None, None, None, None
    K = add1.left.value

    mul = add1.right
    if not (isinstance(mul, ast.BinOp) and isinstance(mul.op, ast.Mult)):
        return None, None, None, None
    if isinstance(mul.right, ast.Constant) and (
            idx_var is None or
            (isinstance(mul.left, ast.Name) and mul.left.id == idx_var)):
        M = mul.right.value
    elif isinstance(mul.left, ast.Constant) and (
            idx_var is None or
            (isinstance(mul.right, ast.Name) and mul.right.id == idx_var)):
        M = mul.left.value
    else:
        return None, None, None, None
    return K, M, N, MOD


# ---------------------------------------------------------------------------
# Trampoline (user function) registration removal
# ---------------------------------------------------------------------------

class TrampolineCleanup(ast.NodeTransformer):
    """Find the pattern:
        def TMP(...): ...
        _ft[KEY] = TMP    # already subbed -> may now be `<orig_name> = TMP`
        del TMP
    We turn that into `def <orig_name>(...): ...`.

    Since TableSubstitutor replaces `_ft[k]` with Name(<builtin>), but user function
    keys live in the *same* table — and we DO have the ft table for builtins, but
    user-function keys are NOT in the ft table (those entries are populated at runtime
    via trampoline). So the user-function keys remain as `_ft[<intkey>]` after substitution.

    We detect:
        def TMP(args): body
        _ft[KEY] = TMP
        del TMP
    and replace with `def NAME_FOR_KEY(args): body`, where NAME_FOR_KEY comes from
    a name-map we build (key -> readable name). Populates self.user_key_to_name in
    place so a later pass can rewrite call sites.
    """
    def __init__(self, ft_varname, user_key_to_name):
        self.ft = ft_varname
        self.user_key_to_name = user_key_to_name

    def visit_Module(self, node):
        # First, walk module body to detect trampoline triplets and populate the
        # key map BEFORE diving into nested defs (so nested defs can call siblings).
        self._discover_keys(node.body)
        node = self.generic_visit(node)
        node.body = self._sweep(node.body)
        return node

    def _discover_keys(self, stmts):
        i = 0
        while i < len(stmts):
            s = stmts[i]
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and i + 2 < len(stmts):
                key = self._match_trampoline(s, stmts[i+1], stmts[i+2])
                if key is not None and key not in self.user_key_to_name:
                    self.user_key_to_name[key] = f"func_{key}"
                    i += 3
                    continue
            i += 1

    def visit_FunctionDef(self, node):
        # don't recurse into function bodies for trampoline collapse — those don't have it
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def _sweep(self, stmts):
        out = []
        i = 0
        while i < len(stmts):
            s = stmts[i]
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and i + 2 < len(stmts):
                assign = stmts[i+1]
                delete = stmts[i+2]
                key = self._match_trampoline(s, assign, delete)
                if key is not None:
                    new_name = self.user_key_to_name.get(key, f"func_{key}")
                    s.name = new_name
                    out.append(s)
                    i += 3
                    continue
            out.append(s)
            i += 1
        return out

    def _match_trampoline(self, fn_def, assign, delete):
        """If the triplet (fn_def, assign, delete) is the trampoline pattern, return
        the integer key from _ft[key]. Else return None."""
        tmp_name = fn_def.name
        # assign: _ft[<int>] = <Name(tmp_name)>
        if not isinstance(assign, ast.Assign):
            return None
        if len(assign.targets) != 1:
            return None
        t = assign.targets[0]
        if not (isinstance(t, ast.Subscript)
                and isinstance(t.value, ast.Name)
                and t.value.id == self.ft
                and isinstance(t.slice, ast.Constant)
                and isinstance(t.slice.value, int)):
            return None
        key = t.slice.value
        if not (isinstance(assign.value, ast.Name) and assign.value.id == tmp_name):
            return None
        # delete: del <Name(tmp_name)>
        if not isinstance(delete, ast.Delete):
            return None
        if len(delete.targets) != 1:
            return None
        if not (isinstance(delete.targets[0], ast.Name)
                and delete.targets[0].id == tmp_name):
            return None
        return key


class UserFuncCallRewrite(ast.NodeTransformer):
    """Replace remaining `_ft[KEY]` Name refs in load context with the user
    function's readable name."""
    def __init__(self, ft_varname, user_key_to_name):
        self.ft = ft_varname
        self.user_key_to_name = user_key_to_name

    def visit_Subscript(self, node):
        node = self.generic_visit(node)
        if (isinstance(node.value, ast.Name)
                and node.value.id == self.ft
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, int)
                and node.slice.value in self.user_key_to_name):
            return ast.copy_location(
                ast.Name(id=self.user_key_to_name[node.slice.value], ctx=node.ctx),
                node,
            )
        return node


# ---------------------------------------------------------------------------
# Rename obfuscated identifiers
# ---------------------------------------------------------------------------

class IdentifierRenamer(ast.NodeTransformer):
    """Rename scrambled identifiers using a provided mapping."""
    def __init__(self, mapping):
        self.mapping = mapping

    def visit_Name(self, node):
        if node.id in self.mapping:
            return ast.copy_location(ast.Name(id=self.mapping[node.id], ctx=node.ctx), node)
        return node

    def visit_arg(self, node):
        if node.arg in self.mapping:
            node.arg = self.mapping[node.arg]
        return node

    def visit_FunctionDef(self, node):
        if node.name in self.mapping:
            node.name = self.mapping[node.name]
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        if node.name in self.mapping:
            node.name = self.mapping[node.name]
        self.generic_visit(node)
        return node


# ---------------------------------------------------------------------------
# Drop top-level `__fref__` placeholders -> turn into lambda/call
# ---------------------------------------------------------------------------

class FrefCleanup(ast.NodeTransformer):
    """Fix `__fref__(<some_iterable>)` call to a no-op (or, better, eliminate the
    surrounding `bytes(__fref__(...)).decode()` once the inner XOR strings have
    been decoded). After XorStringDecoder runs successfully, those calls should
    be gone. This visitor is a safety net to drop any leftover __fref__ usage.
    """
    def visit_Call(self, node):
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "__fref__":
            # Replace the call with its first argument (a generator expression)
            if node.args:
                return node.args[0]
        return node


class DataclassAnnFix(ast.NodeTransformer):
    """For classes decorated with @dataclass, convert bare class-body Assigns into
    AnnAssign with annotation `int` so that dataclass() can find the fields.

    The original source had real type annotations (PEP 649 __annotate__ lambdas)
    but we stripped those during decompilation. Using `int` is a heuristic but it
    matches dataclass's requirement that fields have annotations.
    """
    def visit_ClassDef(self, node):
        self.generic_visit(node)
        if not self._has_dataclass_dec(node):
            return node
        new_body = []
        for stmt in node.body:
            if (isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)):
                # Convert `name = value` to `name: int = value`
                target = stmt.targets[0]
                new_body.append(ast.AnnAssign(
                    target=ast.Name(id=target.id, ctx=ast.Store()),
                    annotation=ast.Name(id="int", ctx=ast.Load()),
                    value=stmt.value,
                    simple=1,
                ))
            else:
                new_body.append(stmt)
        node.body = new_body
        return node

    def _has_dataclass_dec(self, node):
        for d in node.decorator_list:
            if isinstance(d, ast.Name) and d.id == "dataclass":
                return True
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) \
                    and d.func.id == "dataclass":
                return True
        return False


class BoolSimplifier(ast.NodeTransformer):
    """Simplify common boolean idioms produced by the decompiler:
        not X is Y       -> X is not Y
        not X is not Y   -> X is Y
        not X == Y       -> X != Y
        not X != Y       -> X == Y
        not (a and b)    -> (not a) or (not b)  (skipped — keep readable)
    """
    def visit_UnaryOp(self, node):
        node = self.generic_visit(node)
        if isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Compare) \
                and len(node.operand.ops) == 1:
            cmp = node.operand
            op = cmp.ops[0]
            if isinstance(op, ast.Is):
                return ast.Compare(left=cmp.left, ops=[ast.IsNot()],
                                   comparators=cmp.comparators)
            if isinstance(op, ast.IsNot):
                return ast.Compare(left=cmp.left, ops=[ast.Is()],
                                   comparators=cmp.comparators)
            if isinstance(op, ast.Eq):
                return ast.Compare(left=cmp.left, ops=[ast.NotEq()],
                                   comparators=cmp.comparators)
            if isinstance(op, ast.NotEq):
                return ast.Compare(left=cmp.left, ops=[ast.Eq()],
                                   comparators=cmp.comparators)
            if isinstance(op, ast.Lt):
                return ast.Compare(left=cmp.left, ops=[ast.GtE()],
                                   comparators=cmp.comparators)
            if isinstance(op, ast.LtE):
                return ast.Compare(left=cmp.left, ops=[ast.Gt()],
                                   comparators=cmp.comparators)
            if isinstance(op, ast.Gt):
                return ast.Compare(left=cmp.left, ops=[ast.LtE()],
                                   comparators=cmp.comparators)
            if isinstance(op, ast.GtE):
                return ast.Compare(left=cmp.left, ops=[ast.Lt()],
                                   comparators=cmp.comparators)
            if isinstance(op, ast.In):
                return ast.Compare(left=cmp.left, ops=[ast.NotIn()],
                                   comparators=cmp.comparators)
            if isinstance(op, ast.NotIn):
                return ast.Compare(left=cmp.left, ops=[ast.In()],
                                   comparators=cmp.comparators)
        return node


# ---------------------------------------------------------------------------
# Cpp314BuiltinIdentitySimplifier — strip CPython 3.14 `if X is X:` checks
# ---------------------------------------------------------------------------

class Cpp314BuiltinIdentitySimplifier(ast.NodeTransformer):
    """Remove CPython 3.14 builtin-identity optimisation artifacts.

    CPython 3.14 emits: `if builtin is builtin: <fast_path> [<slow_path>]`
    to guard against monkey-patching. The `if X is X:` check is always True.

    We collapse it to just the body. We also drop the `<slow_path>` that
    follows if it takes the form `if True(expr): continue` or `if True(expr): pass`
    (the `True(...)` call is a decompiler artifact for the slow-path `all()`).

    Also removes standalone `all` / `len` / etc expression statements that
    are artefacts of LOAD_GLOBAL before the IS_OP check.
    """

    # Builtins whose identity checks are trivially True
    _BUILTINS = frozenset([
        'all', 'any', 'len', 'map', 'filter', 'zip', 'enumerate', 'sorted',
        'min', 'max', 'sum', 'abs', 'round', 'range', 'reversed', 'list',
        'dict', 'set', 'tuple', 'str', 'int', 'float', 'bool', 'bytes',
        'type', 'isinstance', 'issubclass', 'print', 'repr', 'hash',
        'id', 'iter', 'next', 'open', 'getattr', 'setattr', 'delattr',
        'hasattr', 'callable', 'vars', 'dir',
    ])

    def _is_builtin_identity(self, node):
        """Return True for `X is X` where X is a builtin name."""
        if not (isinstance(node, ast.Compare)
                and len(node.ops) == 1
                and isinstance(node.ops[0], ast.Is)):
            return False
        left = node.left
        right = node.comparators[0]
        return (isinstance(left, ast.Name)
                and isinstance(right, ast.Name)
                and left.id == right.id
                and left.id in self._BUILTINS)

    def _is_slow_path_artifact(self, node):
        """Return True for `if True(expr):` artifacts from the slow path."""
        if not (isinstance(node, ast.If) and not node.orelse):
            return False
        t = node.test
        # `True(expr)` or `not True(expr)` — True is never callable
        if isinstance(t, ast.Call) and isinstance(t.func, ast.Constant) and t.func.value is True:
            return True
        if (isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not)
                and isinstance(t.operand, ast.Call)
                and isinstance(t.operand.func, ast.Constant)
                and t.operand.func.value is True):
            return True
        return False

    def _is_builtin_expr_stmt(self, node):
        """Return True for bare `all` / `len` / etc expression statements."""
        return (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Name)
                and node.value.id in self._BUILTINS)

    def _is_loop_only_body(self, stmts):
        """Return True for fast-path inline loop bodies: `for _loop_val in (genexpr): if not _loop_val: pass`.

        This is a CPython 3.14 optimization artifact — the inline loop is the fast
        path for `all(genexpr)`. Since the slow path (`if all(genexpr): ...`) appears
        immediately after in the decompiled output, we can discard the fast path entirely.
        """
        # Strip leading bare-builtin expression statements (e.g. `all`)
        real = [s for s in stmts if not self._is_builtin_expr_stmt(s)]
        if len(real) != 1 or not isinstance(real[0], ast.For):
            return False
        loop = real[0]
        if not (isinstance(loop.target, ast.Name) and loop.target.id.startswith('_loop_val')):
            return False
        # Body should be `if not _loop_val: pass` (the early-exit check)
        if len(loop.body) != 1 or not isinstance(loop.body[0], ast.If):
            return False
        return True

    def visit_If(self, node):
        node = self.generic_visit(node)
        if self._is_builtin_identity(node.test):
            # CPython 3.14 builtin-identity check is always True.
            # The body is the fast-path inline loop (an artifact we can discard
            # because the equivalent slow-path call `if all(genexpr): ...` appears
            # immediately after in the decompiled output).
            if self._is_loop_only_body(node.body):
                return []  # discard entirely
            # Generic case: keep the body but discard the else (slow path)
            return node.body
        return self._clean_node(node)

    def _clean_body(self, stmts):
        """Remove builtin expr stmts and slow-path artifacts from a statement list."""
        out = []
        for s in stmts:
            if self._is_builtin_expr_stmt(s):
                continue
            if self._is_slow_path_artifact(s):
                continue
            out.append(s)
        return out if out else stmts

    def _clean_node(self, node):
        """Clean body lists in any node that has them."""
        for field in ('body', 'orelse', 'finalbody', 'handlers'):
            val = getattr(node, field, None)
            if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
                cleaned = self._clean_body(val)
                setattr(node, field, cleaned)
        return node

    def visit_FunctionDef(self, node):
        node = self.generic_visit(node)
        return self._clean_node(node)

    def visit_AsyncFunctionDef(self, node):
        node = self.generic_visit(node)
        return self._clean_node(node)

    def visit_For(self, node):
        node = self.generic_visit(node)
        return self._clean_node(node)

    def visit_While(self, node):
        node = self.generic_visit(node)
        return self._clean_node(node)

    def visit_Module(self, node):
        node = self.generic_visit(node)
        return self._clean_node(node)

    def visit_ClassDef(self, node):
        node = self.generic_visit(node)
        return self._clean_node(node)

    def visit_Try(self, node):
        node = self.generic_visit(node)
        return self._clean_node(node)

    def visit_With(self, node):
        node = self.generic_visit(node)
        return self._clean_node(node)


# ---------------------------------------------------------------------------
# TryExceptUnwrapper — remove transparent try/except wrappers
# ---------------------------------------------------------------------------

class TryExceptUnwrapper(ast.NodeTransformer):
    """Remove `try: <body> except ANYTHING: raise` wrappers.

    Round 11 wraps every function body in:
        try:
            <real body>
        except BaseException:
            raise

    This is semantically transparent (the bare `raise` re-raises, so no
    exception handling actually happens). We strip it by replacing the Try
    node with just its body statements.

    A handler qualifies for removal if it contains only a bare `raise`
    (possibly after a POP_TOP no-op or a pass statement).
    """
    def _is_transparent_handler(self, handler: ast.ExceptHandler) -> bool:
        """Return True if this handler is effectively `except X: raise`."""
        body = handler.body
        # Strip leading Pass / trivial Assign / Expr(None) statements
        real = [s for s in body
                if not (isinstance(s, ast.Pass)
                        or (isinstance(s, ast.Expr)
                            and isinstance(s.value, ast.Constant)
                            and s.value.value is None))]
        if len(real) == 1 and isinstance(real[0], ast.Raise) and real[0].exc is None:
            return True
        return False

    def visit_Try(self, node):
        node = self.generic_visit(node)
        if not node.handlers:
            return node
        # All handlers must be transparent for us to strip
        if all(self._is_transparent_handler(h) for h in node.handlers):
            # Also require no else / finalbody that might have side effects
            if not node.orelse and not node.finalbody:
                return node.body if node.body else [ast.Pass()]
        return node


# ---------------------------------------------------------------------------
# ClosureUnwrapper — remove Round 12 closure-capture return pattern
# ---------------------------------------------------------------------------

class ClosureUnwrapper(ast.NodeTransformer):
    """Remove the Round 12 ClosureCaptureTransformer pattern.

    The obfuscator wraps every function's last return as:
        _clXXXX = EXPR
        def _fYYYY():
            return <garbled_freevars_name>   # != _clXXXX due to scrub_code
        return _fYYYY()

    After decompilation the free-variable name inside _fYYYY is garbled
    independently from _clXXXX, so the inner function references a name
    that does not exist in the outer scope.

    We detect the AST pattern:
        Assign(targets=[Name(VAR)], value=EXPR)
        FunctionDef(name=INNER_FN, args=<empty>, body=[Return(Name(FREE_VAR))])
        Return(Call(func=Name(INNER_FN), args=[]))

    and replace the three statements with:
        Return(value=EXPR)

    FREE_VAR may or may not equal VAR — we always use EXPR from the outer
    Assign, ignoring whatever name the inner function references.

    This runs on statement lists at any nesting depth. It should be applied
    BEFORE TryExceptUnwrapper so that it can fire inside try bodies, but it
    also fires correctly after, because we visit recursively.
    """

    def _sweep_stmts(self, stmts):
        """Scan a statement list and collapse closure patterns in-place."""
        out = []
        i = 0
        while i < len(stmts):
            # Look for the triplet: Assign, FunctionDef, Return-call
            if (i + 2 < len(stmts)
                    and self._match_closure_triplet(stmts[i], stmts[i+1], stmts[i+2])):
                assign = stmts[i]
                # Replace with a plain return of the assigned expression
                new_ret = ast.Return(value=assign.value)
                ast.copy_location(new_ret, stmts[i+2])
                ast.fix_missing_locations(new_ret)
                out.append(new_ret)
                i += 3
                continue
            out.append(stmts[i])
            i += 1
        return out

    def _match_closure_triplet(self, s0, s1, s2):
        """Return True if (s0, s1, s2) is the closure-capture triplet.

        Handles both Round 12 (FunctionDef form) and Round 13 (lambda form):

        Round 12:
            _clXXXX = EXPR
            def _fYYYY(): return FREE_VAR
            return _fYYYY()

        Round 13:
            _clXXXX = EXPR
            _fYYYY = lambda _xZZZZ=_clXXXX: _xZZZZ
            return _fYYYY()
        """
        # s0: VAR = EXPR  (single target, any expression)
        if not (isinstance(s0, ast.Assign)
                and len(s0.targets) == 1
                and isinstance(s0.targets[0], ast.Name)):
            return False
        outer_var = s0.targets[0].id

        # Detect s1 form and extract fn_name
        fn_name = None

        # Round 12 form: def INNER_FN(): return FREE_VAR
        # Round 13 compiled lambda form: def INNER_FN(_xZZZZ=_clXXXX): return _xZZZZ
        if isinstance(s1, ast.FunctionDef):
            fn_name = s1.name
            args = s1.args
            # Round 12: no args at all
            if not (args.posonlyargs or args.args or args.vararg
                    or args.kwonlyargs or args.kwarg):
                if len(s1.body) != 1 or not isinstance(s1.body[0], ast.Return):
                    return False
                if not isinstance(s1.body[0].value, ast.Name):
                    return False
            # Round 13 lambda compiled to def: exactly one positional arg with one default
            elif (len(args.args) == 1
                  and len(args.defaults) == 1
                  and not args.posonlyargs
                  and not args.vararg
                  and not args.kwonlyargs
                  and not args.kwarg):
                # Default must reference the outer _cl variable
                default = args.defaults[0]
                if not (isinstance(default, ast.Name) and default.id == outer_var):
                    return False
                # Body must be exactly: return <param_name>
                param_name = args.args[0].arg
                if len(s1.body) != 1 or not isinstance(s1.body[0], ast.Return):
                    return False
                ret_val = s1.body[0].value
                if not (isinstance(ret_val, ast.Name) and ret_val.id == param_name):
                    return False
            else:
                return False

        # Round 13 form: _fYYYY = lambda _xZZZZ=_clXXXX: _xZZZZ
        elif (isinstance(s1, ast.Assign)
              and len(s1.targets) == 1
              and isinstance(s1.targets[0], ast.Name)
              and isinstance(s1.value, ast.Lambda)):
            fn_name = s1.targets[0].id
            lam = s1.value
            lam_args = lam.args
            # Lambda must have exactly one arg with one default (the outer var)
            if (len(lam_args.args) != 1
                    or len(lam_args.defaults) != 1
                    or lam_args.posonlyargs
                    or lam_args.vararg
                    or lam_args.kwonlyargs
                    or lam_args.kwarg):
                return False
            # Default must reference the outer _cl variable
            default = lam_args.defaults[0]
            if not (isinstance(default, ast.Name) and default.id == outer_var):
                return False
            # Body must be a Name (the parameter)
            if not isinstance(lam.body, ast.Name):
                return False
        else:
            return False

        # s2: return INNER_FN()
        if not isinstance(s2, ast.Return):
            return False
        call = s2.value
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == fn_name
                and not call.args
                and not call.keywords):
            return False

        return True

    # Apply to any node that holds a list of statements.

    def _visit_body(self, stmts):
        # First recurse into children, then sweep at this level.
        new = []
        for s in stmts:
            visited = self.visit(s)
            if isinstance(visited, list):
                new.extend(visited)
            elif visited is not None:
                new.append(visited)
        return self._sweep_stmts(new)

    def visit_Module(self, node):
        node.body = self._visit_body(node.body)
        return node

    def visit_FunctionDef(self, node):
        node.body = self._visit_body(node.body)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        node.body = self._visit_body(node.body)
        return node

    def visit_If(self, node):
        node.body = self._visit_body(node.body)
        node.orelse = self._visit_body(node.orelse)
        return node

    def visit_For(self, node):
        node.body = self._visit_body(node.body)
        node.orelse = self._visit_body(node.orelse)
        return node

    def visit_While(self, node):
        node.body = self._visit_body(node.body)
        node.orelse = self._visit_body(node.orelse)
        return node

    def visit_Try(self, node):
        node.body = self._visit_body(node.body)
        node.orelse = self._visit_body(node.orelse)
        node.finalbody = self._visit_body(node.finalbody)
        for handler in node.handlers:
            handler.body = self._visit_body(handler.body)
        return node

    def visit_With(self, node):
        node.body = self._visit_body(node.body)
        return node


# ---------------------------------------------------------------------------
# FreevarResolver — fix garbled free variable names in genexps and lambdas
# ---------------------------------------------------------------------------

class FreevarResolver:
    """Build a rename map for garbled freevar names by tracing bytecode.

    When scrub_code() garbles co_freevars (child) and co_cellvars (parent)
    with independent salts, the name in the child's body that came from
    LOAD_DEREF doesn't match the name in the parent's scope.

    We recover the correct mapping by:
    1. For each code object, find all MAKE_FUNCTION/SET_FUNCTION_ATTRIBUTE
       closure sequences in its bytecode.
    2. Each such sequence pushes a tuple of cell/fast values onto the stack
       then attaches them as the closure of a code-const.
    3. The order of values in that tuple matches co_freevars in the child code.
    4. We build freevar_name -> outer_scope_name mapping and store it by
       child code object id().

    Then we apply the mapping as a rename to the decompiled AST, restricted
    to the AST subtree that came from the given code object.
    """

    def __init__(self, root_code):
        self.mapping: dict[int, dict[str, str]] = {}  # code_id -> {freevar: outer_name}
        self._build(root_code)

    def _build(self, co):
        """Recursively analyse code object and its nested code objects."""
        import dis
        instructions = list(dis.get_instructions(co))
        # Map code object ids from co_consts for quick lookup
        code_consts = {}
        for c in co.co_consts:
            if hasattr(c, 'co_code') and c.co_freevars:
                code_consts[id(c)] = c

        # Simulate a simplified value stack to track what's pushed before
        # SET_FUNCTION_ATTRIBUTE closure. We only care about LOAD_FAST_BORROW,
        # LOAD_FAST, LOAD_DEREF, LOAD_CLASSDEREF, LOAD_GLOBAL, and BUILD_TUPLE.
        i = 0
        while i < len(instructions):
            instr = instructions[i]
            if (instr.opname == 'SET_FUNCTION_ATTRIBUTE'
                    and instr.argrepr == 'closure'
                    or (instr.opname == 'SET_FUNCTION_ATTRIBUTE'
                        and instr.argval == 8)):
                # The stack before SET_FUNCTION_ATTRIBUTE has:
                #   TOS  = func (result of MAKE_FUNCTION)
                #   TOS1 = closure tuple (result of BUILD_TUPLE)
                # We need to find the MAKE_FUNCTION and BUILD_TUPLE before it.
                # Walk backwards to find the closure tuple construction.
                j = i - 1
                # skip the MAKE_FUNCTION
                while j >= 0 and instructions[j].opname != 'MAKE_FUNCTION':
                    j -= 1
                if j < 0:
                    i += 1
                    continue
                make_fn_idx = j
                # The MAKE_FUNCTION is preceded by the code const load.
                # Before that is the BUILD_TUPLE for the closure.
                # Actually the order in CPython 3.14 is:
                #   ... (load free vars) BUILD_TUPLE N LOAD_CONST <code> MAKE_FUNCTION
                #   SET_FUNCTION_ATTRIBUTE
                # Find BUILD_TUPLE before MAKE_FUNCTION
                k = make_fn_idx - 1
                # Skip LOAD_CONST (the code object itself)
                while k >= 0 and instructions[k].opname == 'LOAD_CONST':
                    k -= 1
                if k < 0 or instructions[k].opname != 'BUILD_TUPLE':
                    i += 1
                    continue
                build_tuple_idx = k
                n_freevars = instructions[build_tuple_idx].argval
                # Collect the N LOAD_* instructions before BUILD_TUPLE
                load_instrs = instructions[build_tuple_idx - n_freevars: build_tuple_idx]
                outer_names = []
                for li in load_instrs:
                    if li.opname in ('LOAD_FAST_BORROW', 'LOAD_FAST',
                                     'LOAD_DEREF', 'LOAD_CLASSDEREF'):
                        outer_names.append(li.argval)
                    elif li.opname == 'LOAD_GLOBAL':
                        outer_names.append(li.argval)
                    else:
                        outer_names.append(None)

                # Find the code const that MAKE_FUNCTION will use.
                # It's the LOAD_CONST just before MAKE_FUNCTION.
                code_load_idx = make_fn_idx - 1
                while code_load_idx >= 0 and instructions[code_load_idx].opname != 'LOAD_CONST':
                    code_load_idx -= 1
                if code_load_idx < 0:
                    i += 1
                    continue
                child_co = instructions[code_load_idx].argval
                if not hasattr(child_co, 'co_freevars'):
                    i += 1
                    continue
                child_freevars = child_co.co_freevars
                if len(outer_names) == len(child_freevars):
                    mapping = {}
                    for fv, ov in zip(child_freevars, outer_names):
                        if ov is not None and fv != ov:
                            mapping[fv] = ov
                    if mapping:
                        self.mapping[id(child_co)] = mapping
            i += 1

        # Recurse into nested code objects
        for c in co.co_consts:
            if hasattr(c, 'co_code'):
                self._build(c)

    def get_mapping_for_code(self, co) -> dict[str, str]:
        """Return the freevar -> outer_name mapping for a specific code object."""
        return self.mapping.get(id(co), {})
