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
]


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
    # NaN-identity composite: x is not None and x != x — generated as
    #   BoolOp(And, [Compare(x, IsNot, None), Compare(x, NotEq, x)])
    # or, since our decompiler emits nested If: nested handled separately below
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        # check second clause is `x != x` form
        if any(_is_self_neq(v) for v in node.values):
            return True
    if _is_self_neq(node):
        return True
    # impossible bound like x < 0 with x non-negative — too risky to remove statically without
    # tracking; the obfuscator's other patterns we don't try to remove without proof.
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


def _matches_other_dead_check(node):
    """Recognize:
        if x < 0:
            return None / raise OverflowError(repr(...))
        if x > NNN:
            return x
        if (len(empty) > NNN): ...
    These are the dead-code injections from the obfuscator.
    """
    if not isinstance(node, ast.If):
        return False

    test = node.test
    # `if x < <small_int>:` where <small_int> is <= 0 → likely dead (bounds check on
    # a tracked non-negative var)
    if (isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Lt)
            and isinstance(test.comparators[0], ast.Constant)
            and isinstance(test.comparators[0].value, int)
            and test.comparators[0].value <= 0):
        # body must be a return / raise — and only a single statement that doesn't carry state
        if len(node.body) == 1 and isinstance(node.body[0], (ast.Return, ast.Raise)):
            return True

    # `if x > <large_int>:` body return → dead
    if (isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Gt)
            and isinstance(test.comparators[0], ast.Constant)
            and isinstance(test.comparators[0].value, int)
            and test.comparators[0].value >= 200):
        if len(node.body) == 1 and isinstance(node.body[0], (ast.Return, ast.Raise)):
            return True

    # `if len(<name>) > NNN:` body return → dead
    if (isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Gt)
            and isinstance(test.left, ast.Call)
            and isinstance(test.left.func, ast.Name)
            and test.left.func.id == "len"
            and isinstance(test.comparators[0], ast.Constant)
            and isinstance(test.comparators[0].value, int)
            and test.comparators[0].value >= 100):
        if len(node.body) == 1 and isinstance(node.body[0], (ast.Return, ast.Raise)):
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
