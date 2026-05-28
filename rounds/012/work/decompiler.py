"""Custom decompiler for Python 3.14 bytecode produced by the byepy r008 obfuscator.

The obfuscator chain is: source -> ast transforms -> ast.unparse -> compile.
Therefore the bytecode is well-structured (no weird optimisation chains, no try/except
in the trivial samples). We walk the bytecode in straight-line basic blocks, maintain
an evaluation stack of AST expressions, and emit statements when we hit STORE/RETURN/
POP_TOP/JUMP/etc. The result is a Python AST that we can feed to ast.unparse() to get
source.

This handles all opcodes observed in the round 8 trivial+medium+csvkit corpus. New
opcodes raise NotImplementedError so we know what to add.
"""
import ast
import dis
import sys
import types
from dataclasses import dataclass, field


# Module-level freevar resolver — set by recover.py before decompiling a file
# that has closure-captured freevars needing rename (e.g. genexps, lambdas).
_current_freevar_resolver = None


# ---------------------------------------------------------------------------
# binop / compare op tables
# ---------------------------------------------------------------------------

BINOP_MAP = {
    0:  ast.Add(),
    1:  ast.BitAnd(),
    2:  ast.FloorDiv(),
    3:  ast.LShift(),
    4:  ast.MatMult(),
    5:  ast.Mult(),
    6:  ast.Mod(),
    7:  ast.BitOr(),
    8:  ast.Pow(),
    9:  ast.RShift(),
    10: ast.Sub(),
    11: ast.Div(),
    12: ast.BitXor(),
    13: ast.Add(),    # in-place
    14: ast.BitAnd(),
    15: ast.FloorDiv(),
    16: ast.LShift(),
    17: ast.MatMult(),
    18: ast.Mult(),
    19: ast.Mod(),
    20: ast.BitOr(),
    21: ast.Pow(),
    22: ast.RShift(),
    23: ast.Sub(),
    24: ast.Div(),
    25: ast.BitXor(),
    26: "subscr",     # BINARY_OP 26 means a[b]
}

# COMPARE_OP arg is (flag << 5) | op_idx but actually 3.14 uses different encoding.
# From CPython 3.14 source: arg = (mask << 5) | (cmp << 4) | (mask>>3?)
# Easier: dis.cmp_op already gives us readable name in instruction.argrepr.
# We'll parse argrepr like 'bool(<)' or '<', '==', etc.
COMPARE_OPS = {
    "<":  ast.Lt(),
    "<=": ast.LtE(),
    "==": ast.Eq(),
    "!=": ast.NotEq(),
    ">":  ast.Gt(),
    ">=": ast.GtE(),
}

# CALL_INTRINSIC_1 args
INTRINSIC_1 = {
    "INTRINSIC_STOPITERATION_ERROR": "stopiter_error",
    "INTRINSIC_ASYNC_GEN_WRAP": "agen_wrap",
}


# ---------------------------------------------------------------------------
# Decompiler
# ---------------------------------------------------------------------------

class _Block:
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.stmts = []


def _normalize_compare_op(argrepr):
    # argrepr can be like "bool(<)", "bool(==)", "<", "==", "<="
    s = argrepr
    if s.startswith("bool(") and s.endswith(")"):
        s = s[5:-1]
    return s


def _name(name):
    return ast.Name(id=name, ctx=ast.Load())


def _const(v):
    return ast.Constant(value=v)


def decompile_code(code: types.CodeType, is_module=False) -> ast.AST:
    """Top-level: decompile a code object into an AST module/function body."""
    body = _decompile_body(code, is_module=is_module)
    if is_module:
        mod = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(mod)
        return mod
    return body


def _make_function_def(code: types.CodeType, name: str, defaults=None,
                       kw_defaults=None) -> ast.FunctionDef:
    """Build an ast.FunctionDef for the given code object using its co_varnames as args."""
    n_pos = code.co_argcount
    n_kw = code.co_kwonlyargcount
    flags = code.co_flags
    has_vararg = bool(flags & 0x04)
    has_kwarg = bool(flags & 0x08)
    varnames = list(code.co_varnames)

    args = [ast.arg(arg=v) for v in varnames[:n_pos]]
    kwonly = [ast.arg(arg=v) for v in varnames[n_pos:n_pos+n_kw]]
    idx = n_pos + n_kw
    vararg = None
    if has_vararg:
        vararg = ast.arg(arg=varnames[idx])
        idx += 1
    kwarg = None
    if has_kwarg:
        kwarg = ast.arg(arg=varnames[idx])
        idx += 1

    body = _decompile_body(code, is_module=False)
    if not body:
        body = [ast.Pass()]
    return ast.FunctionDef(
        name=name,
        args=ast.arguments(
            posonlyargs=[],
            args=args,
            vararg=vararg,
            kwonlyargs=kwonly,
            kw_defaults=kw_defaults or [],
            kwarg=kwarg,
            defaults=defaults or [],
        ),
        body=body,
        decorator_list=[],
        returns=None,
        type_params=[],
    )


# ---------------------------------------------------------------------------
# The heavy lifting: bytecode walker
# ---------------------------------------------------------------------------

class Decompiler:
    def __init__(self, code: types.CodeType, is_module=False):
        self.code = code
        self.is_module = is_module
        self.instructions = list(dis.get_instructions(code))
        # Map offset -> index in instructions list
        self.idx_for_offset = {ins.offset: i for i, ins in enumerate(self.instructions)}
        self.stack: list = []
        self.body: list = []
        # Generator/yield flag
        self.is_generator = bool(code.co_flags & 0x20)
        # Set of known exception handler start offsets (populated by _decompile_body)
        self.handler_offsets: set = set()
        # Freevar resolver for genexp/lambda closure renaming
        self._freevar_resolver = _current_freevar_resolver

        # Cache of jump targets (set of offsets)
        self.jump_targets = set()
        for ins in self.instructions:
            if ins.opname == "FOR_ITER" or ins.opname.startswith("POP_JUMP_IF") \
                    or ins.opname in ("JUMP_FORWARD", "JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT"):
                self.jump_targets.add(ins.argval)

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def run(self):
        i = 0
        i = self._walk(0, len(self.instructions))
        return self.body

    def _is_unreachable_trailer(self, i):
        """Heuristic: from index i to the end, do we see only SWAP/POP_TOP/RERAISE-style
        cleanup or is there actually reachable code? We say "unreachable" if we hit
        a RERAISE/STORE_FAST_RERAISE or only see opcodes that are part of the inlined
        try/except handler that catches exceptions in inlined comprehensions."""
        if i < len(self.instructions):
            # If the next instruction is a known exception handler start, the remaining
            # code is not reachable via fall-through from a RETURN.
            if self.instructions[i].offset in self.handler_offsets:
                return True
        only_cleanup = True
        for k in range(i, len(self.instructions)):
            op = self.instructions[k].opname
            if op == "RERAISE":
                return True
            if op in ("SWAP", "POP_TOP", "STORE_FAST", "STORE_NAME",
                       "CACHE", "NOP", "NOT_TAKEN"):
                continue
            only_cleanup = False
            break
        return only_cleanup

    def _try_inline_comp(self, i, end, container_kind):
        """Detect the inline-comprehension pattern starting at index i:

            <build outer iter>
            GET_ITER
            LOAD_FAST_AND_CLEAR <accum_slot>
            SWAP 2
            BUILD_LIST 0 / BUILD_MAP 0 / BUILD_SET 0
            SWAP 2
            FOR_ITER <end_offset>
                <store loop var>
                <compute elt>
                LIST_APPEND <n> / SET_ADD <n> / MAP_ADD <n>
                JUMP_BACKWARD
            END_FOR ; POP_ITER
            SWAP 2
            STORE_FAST <accum_slot>

        If matched, builds a ListComp/SetComp/DictComp on the stack and returns the
        new index. Otherwise returns None.

        Called when we observe `GET_ITER ; LOAD_FAST_AND_CLEAR`.
        """
        ins = self.instructions
        if ins[i].opname != "LOAD_FAST_AND_CLEAR":
            return None
        accum_slot = ins[i].argval
        # Skip any additional LOAD_FAST_AND_CLEAR ops (one per loop var saved)
        k = i + 1
        extra_clears = 0
        while k < end and ins[k].opname == "LOAD_FAST_AND_CLEAR":
            extra_clears += 1
            k += 1
        # SWAP <n> where n = extra_clears + 2 (or 2 in the simple case)
        if k >= end or ins[k].opname != "SWAP":
            return None
        swap_arg = ins[k].arg
        k += 1
        if k >= end or ins[k].opname not in ("BUILD_LIST", "BUILD_SET", "BUILD_MAP"):
            return None
        build_op = ins[k].opname
        if ins[k].arg != 0:
            return None
        kind = {
            "BUILD_LIST": "list",
            "BUILD_SET": "set",
            "BUILD_MAP": "dict",
        }[build_op]
        k += 1
        if k >= end or ins[k].opname != "SWAP" or ins[k].arg != 2:
            return None
        k += 1
        if k >= end or ins[k].opname != "FOR_ITER":
            return None
        for_iter_idx = k
        for_iter_ins = ins[for_iter_idx]
        loop_end_offset = for_iter_ins.argval
        loop_end_idx = self.idx_for_offset[loop_end_offset]

        # The outermost iter is on the top of our AST stack. Pop it.
        outer_iter = self.stack.pop()

        # Parse the loop variable
        body_first = for_iter_idx + 1
        while body_first < end and ins[body_first].opname in ("NOT_TAKEN", "NOP", "CACHE"):
            body_first += 1

        # Save stack BEFORE consume_for_target because STORE_FAST_LOAD_FAST etc. may
        # push values onto parent.stack while consuming the loop-var instruction.
        saved_stack = list(self.stack)
        saved_body = self.body
        self.stack = []
        self.body = []

        sub_helper = _SubDecompiler(self)
        target_node = _consume_for_target(sub_helper, self, body_first)
        body_first = sub_helper._next_idx
        j = body_first
        elt = None
        value_pair = None
        if_filter = None
        while j < loop_end_idx:
            t_ins = ins[j]
            t_op = t_ins.opname
            if t_op == "LIST_APPEND" and kind == "list":
                elt = self.stack.pop()
                j += 1
                break
            if t_op == "SET_ADD" and kind == "set":
                elt = self.stack.pop()
                j += 1
                break
            if t_op == "MAP_ADD" and kind == "dict":
                v = self.stack.pop()
                k = self.stack.pop()
                value_pair = (k, v)
                j += 1
                break
            if t_op in ("POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE",
                         "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE"):
                cond = self.stack.pop()
                # Check the following pattern
                k2 = j + 1
                while k2 < loop_end_idx and ins[k2].opname == "NOT_TAKEN":
                    k2 += 1
                if (k2 < loop_end_idx
                        and ins[k2].opname.startswith("JUMP_BACKWARD")
                        and t_ins.argval is not None):
                    # Filter pattern: POP_JUMP_IF + JUMP_BACKWARD — body at target
                    target_idx_inner = self.idx_for_offset[t_ins.argval]
                    if t_op == "POP_JUMP_IF_TRUE":
                        if_filter = cond
                    elif t_op == "POP_JUMP_IF_FALSE":
                        if_filter = ast.UnaryOp(op=ast.Not(), operand=cond)
                    elif t_op == "POP_JUMP_IF_NONE":
                        if_filter = ast.Compare(left=cond, ops=[ast.IsNot()],
                                                comparators=[_const(None)])
                    elif t_op == "POP_JUMP_IF_NOT_NONE":
                        if_filter = ast.Compare(left=cond, ops=[ast.Is()],
                                                comparators=[_const(None)])
                    j = target_idx_inner
                    continue
                # Check for ternary pattern: POP_JUMP_IF <else_target> ; <true_body> ;
                # JUMP_FORWARD <merge> ; <else_body> ; merge: LIST_APPEND/SET_ADD/MAP_ADD
                # The POP_JUMP target (else_target) should be inside the loop body.
                if t_ins.argval is not None and t_ins.argval in self.idx_for_offset:
                    else_start = self.idx_for_offset[t_ins.argval]
                    # Walk true branch from j+1 to else_start-1 collecting the true expr
                    true_stack_save = list(self.stack)
                    # Execute instructions in the true branch
                    tj = k2
                    true_expr = None
                    while tj < else_start:
                        t2_ins = ins[tj]
                        t2_op = t2_ins.opname
                        if t2_op == "JUMP_FORWARD":
                            # End of true branch — JUMP_FORWARD to merge point
                            # The merge point is after the else branch
                            true_expr = self.stack.pop() if self.stack else None
                            # Restore stack to pre-true-branch state for else branch
                            self.stack[:] = true_stack_save
                            # Walk else branch from else_start
                            ej = else_start
                            while ej < loop_end_idx:
                                e_ins = ins[ej]
                                if e_ins.opname in ("LIST_APPEND", "SET_ADD", "MAP_ADD"):
                                    break
                                if e_ins.opname in ("RESUME", "CACHE", "NOT_TAKEN", "NOP", "JUMP_BACKWARD"):
                                    ej += 1
                                    continue
                                ej = self._exec_inst(ej)
                            else_expr = self.stack.pop() if self.stack else _const(None)
                            self.stack[:] = true_stack_save
                            # Build ternary: true_expr if cond is not None else else_expr
                            if t_op in ("POP_JUMP_IF_NONE",):
                                # Jump to else when None: true_expr if x is not None else else_expr
                                ternary = ast.IfExp(
                                    test=ast.Compare(left=cond, ops=[ast.IsNot()], comparators=[_const(None)]),
                                    body=true_expr if true_expr is not None else _const(None),
                                    orelse=else_expr,
                                )
                            elif t_op in ("POP_JUMP_IF_NOT_NONE",):
                                ternary = ast.IfExp(
                                    test=ast.Compare(left=cond, ops=[ast.Is()], comparators=[_const(None)]),
                                    body=true_expr if true_expr is not None else _const(None),
                                    orelse=else_expr,
                                )
                            elif t_op == "POP_JUMP_IF_FALSE":
                                ternary = ast.IfExp(test=cond,
                                                    body=true_expr if true_expr is not None else _const(None),
                                                    orelse=else_expr)
                            else:  # POP_JUMP_IF_TRUE
                                ternary = ast.IfExp(test=ast.UnaryOp(op=ast.Not(), operand=cond),
                                                    body=true_expr if true_expr is not None else _const(None),
                                                    orelse=else_expr)
                            self.stack.append(ternary)
                            # Skip to after else branch (the JUMP_FORWARD target is t2_ins.argval)
                            j = self.idx_for_offset.get(t2_ins.argval, ej)
                            break
                        elif t2_op in ("RESUME", "CACHE", "NOT_TAKEN", "NOP"):
                            tj += 1
                        else:
                            tj = self._exec_inst(tj)
                    else:
                        # Didn't find JUMP_FORWARD in true branch — fall through
                        j += 1
                    continue
                j += 1
                continue
            if t_op == "JUMP_FORWARD":
                # Forward jump inside element body — skip to the target.
                target_offset = t_ins.argval
                if target_offset in self.idx_for_offset:
                    j = self.idx_for_offset[target_offset]
                else:
                    j += 1
                continue
            if t_op in ("RESUME", "CACHE", "NOT_TAKEN", "NOP"):
                j += 1
                continue
            j = self._exec_inst(j)
        self.stack = saved_stack
        self.body = saved_body

        # Build the comprehension node first (needed for both patterns below)
        if elt is None and value_pair is None:
            return None
        ifs = [if_filter] if if_filter is not None else []
        comp = ast.comprehension(target=target_node, iter=outer_iter, ifs=ifs, is_async=0)
        if kind == "list":
            node = ast.ListComp(elt=elt, generators=[comp])
        elif kind == "set":
            node = ast.SetComp(elt=elt, generators=[comp])
        else:
            k_node, v_node = value_pair
            node = ast.DictComp(key=k_node, value=v_node, generators=[comp])

        # Skip to after END_FOR/POP_ITER. Then handle the post-comp pattern.
        # Two patterns observed:
        #   A: SWAP <N> ; STORE_FAST x (N-1 times)  -- comp_result remains for next op
        #   B: STORE_FAST <accum_slot> ; STORE_FAST <orig_slot> -- comp_result stored to local
        while j < end and ins[j].opname in (
                "JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT",
                "END_FOR", "POP_ITER"):
            j += 1
        # Pattern A: SWAP N ; (N-1) STORE_FAST/STORE_NAME
        if j < end and ins[j].opname == "SWAP":
            swap_n = ins[j].arg
            j += 1
            for _ in range(swap_n - 1):
                if j < end and ins[j].opname in ("STORE_FAST", "STORE_NAME"):
                    j += 1
                else:
                    break
            self.stack.append(node)
            return j
        # Pattern B: STORE_FAST <accum_slot> followed by 0+ "restore" STOREs
        if j < end and ins[j].opname in ("STORE_FAST", "STORE_NAME"):
            target = _store_name(ins[j].argval)
            self.body.append(ast.Assign(targets=[target], value=node))
            j += 1
            # Consume any additional restore STOREs (these had values from LFAC sentinels
            # we did not track)
            while j < end and ins[j].opname in ("STORE_FAST", "STORE_NAME"):
                j += 1
            return j
        # Fallback: leave comp on stack
        self.stack.append(node)
        return j

    # ------------------------------------------------------------------
    # Walker — appends statements to self.body, returns next index
    # ------------------------------------------------------------------
    def _walk(self, start, end):
        i = start
        while i < end:
            ins = self.instructions[i]
            op = ins.opname

            # ---- Structured: with statement ----
            # Pattern: <cm_expr> COPY 1 LOAD_SPECIAL 1 SWAP 2 SWAP 3 LOAD_SPECIAL 0 CALL 0 STORE_*
            if op == "COPY" and i + 6 < end \
                    and self.instructions[i+1].opname == "LOAD_SPECIAL" \
                    and self.instructions[i+1].arg == 1:
                i = self._with_stmt(i, end)
                continue

            # ---- Structured: FOR_ITER body ----
            if op == "FOR_ITER":
                # Stack top: iterable. After GET_ITER ... FOR_ITER, the loop body
                # follows until JUMP_BACKWARD back to this FOR_ITER. After the loop,
                # we see END_FOR/POP_ITER (or similar) at the jump target.
                i = self._for_loop(i, end)
                continue

            # ---- Structured: WHILE True via state-machine CFF (not handled here) ----
            # The CFF transforms produce a while True: if state == ... else: ...
            # The bytecode for that looks like: load state, compare, pop_jump.
            # We treat it as regular if/else and let the AST cleanup pass collapse it.

            # ---- Conditional jumps -> if/else ----
            if op in ("POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE",
                      "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE"):
                i = self._if_else(i, end)
                continue

            if op in ("JUMP_FORWARD", "JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT"):
                # Backward jump at this scope means a loop boundary handled by caller.
                # Forward jump means a branch boundary, also caller's problem.
                return i

            if op == "RETURN_VALUE":
                value = self.stack.pop()
                self.body.append(ast.Return(value=value))
                i += 1
                # If we're at the top of a function body and the stack is empty,
                # check whether the rest of the code is unreachable (exception-handler
                # trailer). If so, stop walking.
                if not self.stack and self._is_unreachable_trailer(i):
                    return i
                continue

            if op == "RETURN_CONST":
                self.body.append(ast.Return(value=_const(ins.argval)))
                i += 1
                if not self.stack and self._is_unreachable_trailer(i):
                    return i
                continue

            if op == "END_FOR" or op == "POP_ITER" or op == "POP_BLOCK":
                # Boundary marker — caller handles
                return i

            # ---- Default: handle one instruction ----
            try:
                i = self._exec_inst(i)
            except (IndexError, AssertionError, NotImplementedError, AttributeError, TypeError) as e:
                # Emit a placeholder and move on so we can at least produce something.
                self.body.append(ast.Expr(value=ast.Call(
                    func=ast.Name(id="__decode_failed__", ctx=ast.Load()),
                    args=[ast.Constant(value=f"{op}@{ins.offset}:{type(e).__name__}")],
                    keywords=[]
                )))
                i += 1
        return i

    # ------------------------------------------------------------------
    # Single instruction handler — stack manipulation
    # ------------------------------------------------------------------
    def _exec_inst(self, i):
        ins = self.instructions[i]
        op = ins.opname
        arg = ins.arg
        argval = ins.argval

        # nops / housekeeping
        if op in ("RESUME", "CACHE", "PRECALL", "NOT_TAKEN",
                  "MAKE_CELL", "COPY_FREE_VARS", "RETURN_GENERATOR"):
            return i + 1

        if op == "PUSH_NULL":
            self.stack.append(_NullMarker())
            return i + 1

        # ---- LOADs ----
        if op == "LOAD_CONST":
            v = ins.argval
            if isinstance(v, types.CodeType):
                self.stack.append(_CodeObj(v))
            else:
                self.stack.append(_const(v))
            return i + 1
        if op == "LOAD_SMALL_INT":
            self.stack.append(_const(arg))
            return i + 1
        if op in ("LOAD_NAME", "LOAD_FAST", "LOAD_FAST_BORROW",
                  "LOAD_DEREF", "LOAD_CLASSDEREF", "LOAD_FAST_CHECK"):
            self.stack.append(_name(ins.argval))
            return i + 1
        if op == "LOAD_FAST_AND_CLEAR":
            # Push a sentinel that we'll consume in the matching STORE_FAST after
            # the inline comprehension. Using the name lets later passes detect a
            # benign no-op.
            self.stack.append(_LoadFastAndClearSentinel(ins.argval))
            return i + 1
        if op == "LOAD_GLOBAL":
            # In CPython 3.13+, LOAD_GLOBAL with the NULL flag (bit 0 of arg) pushes
            # the global first and then NULL on top. So stack ends [..., global, NULL].
            self.stack.append(_name(_strip_null(ins.argval)))
            if isinstance(arg, int) and arg & 1:
                self.stack.append(_NullMarker())
            return i + 1
        if op == "LOAD_FAST_LOAD_FAST" or op == "LOAD_FAST_BORROW_LOAD_FAST_BORROW":
            # Loads two locals from a packed arg, the names are in argrepr "a, b" or argval ('a','b')
            if isinstance(ins.argval, tuple):
                a, b = ins.argval
            else:
                a, b = ins.argrepr.split(",")
                a = a.strip(); b = b.strip()
            self.stack.append(_name(a))
            self.stack.append(_name(b))
            return i + 1
        if op == "LOAD_ATTR":
            obj = self.stack.pop()
            attr = _strip_null(ins.argval)
            attr_node = ast.Attribute(value=obj, attr=attr, ctx=ast.Load())
            # If LOAD_ATTR has the LOAD_ATTR_PUSH_NULL flag (arg bit 0 = 1),
            # it pushes (attr, NULL) for unbound-method dispatch. We track this so
            # CALL knows to read attr as callable and treat the next item as `self`.
            # In CPython 3.13+, the arg encodes: low bit = NULL push flag.
            # In 3.14 dis output, argrepr ends with "+ NULL|self" for the method case.
            if "NULL|self" in (ins.argrepr or ""):
                # bound-method shape: push the unbound attr THEN self
                # actually: after LOAD_ATTR (with bound-method opt), the stack is:
                #   [..., callable, self]
                # so we push the callable then duplicate the receiver as self.
                # But the original `obj` is also `self`. We push attr then obj.
                self.stack.append(attr_node)
                self.stack.append(obj)  # self for the upcoming method call
            else:
                self.stack.append(attr_node)
            return i + 1
        if op == "LOAD_BUILD_CLASS":
            self.stack.append(_BuildClassMarker())
            return i + 1
        if op == "LOAD_ASSERTION_ERROR":
            self.stack.append(_name("AssertionError"))
            return i + 1
        if op == "LOAD_LOCALS":
            self.stack.append(ast.Call(
                func=_name("locals"), args=[], keywords=[]))
            return i + 1
        if op == "LOAD_SUPER_ATTR":
            # specialized form — not expected in our corpus
            obj = self.stack.pop()
            self.stack.append(ast.Attribute(value=obj, attr=ins.argval, ctx=ast.Load()))
            return i + 1
        if op == "LOAD_COMMON_CONSTANT":
            # In 3.14, LOAD_COMMON_CONSTANT is used for built-in identity checks
            # (e.g. `LOAD_GLOBAL all; COPY 1; LOAD_COMMON_CONSTANT all; IS_OP 0;
            # POP_JUMP_IF_FALSE slow_path`). The argval is the constant name from
            # _PyEval_CommonConstantTable. Often it's an exception class name like
            # "AssertionError" or a builtin like "<built-in function all>".
            if isinstance(ins.argval, str):
                self.stack.append(_name(ins.argval))
            else:
                # Get the name via the argrepr (e.g., "<built-in function all>")
                rep = ins.argrepr
                if rep.startswith("<built-in function "):
                    name = rep[len("<built-in function "):-1]
                    self.stack.append(_name(name))
                elif "Error" in rep or "Exception" in rep:
                    self.stack.append(_name(rep))
                else:
                    self.stack.append(_name(f"__common_{arg}__"))
            return i + 1

        # ---- STOREs ----
        if op == "STORE_NAME" or op == "STORE_FAST" or op == "STORE_GLOBAL" or op == "STORE_DEREF":
            value = self.stack.pop()
            # If we're storing the LOAD_FAST_AND_CLEAR sentinel back, treat it as a no-op
            if isinstance(value, _LoadFastAndClearSentinel):
                return i + 1
            # Imports get specialised AST nodes
            if isinstance(value, _ImportRef):
                # `import module` (possibly `as alias`) or `from module import ...` after
                # a series of IMPORT_FROM ops (those don't reach STORE_NAME for the mod ref,
                # only for the imported names).
                store_name = ins.argval
                if value.fromlist is None:
                    # `import a.b.c` stores `a` by default — but if we have an
                    # `import a.b.c as x` the store name differs from the head of the
                    # dotted name. Emit Import accordingly.
                    head = value.module.split(".")[0]
                    if head == store_name:
                        self.body.append(ast.Import(names=[ast.alias(name=value.module, asname=None)]))
                    else:
                        self.body.append(ast.Import(names=[ast.alias(name=value.module, asname=store_name)]))
                else:
                    # Empty fromlist means `import module` semantically equivalent
                    self.body.append(ast.Import(names=[ast.alias(name=value.module, asname=store_name if store_name != value.module else None)]))
                return i + 1
            if isinstance(value, _ImportFromAttr):
                # `from module import name [as alias]`
                store_name = ins.argval
                mod_name = value.mod_ref.module if isinstance(value.mod_ref, _ImportRef) else "<?>"
                asname = None if store_name == value.name else store_name
                level = value.mod_ref.level if isinstance(value.mod_ref, _ImportRef) else 0
                self.body.append(ast.ImportFrom(
                    module=mod_name,
                    names=[ast.alias(name=value.name, asname=asname)],
                    level=level,
                ))
                return i + 1
            # If we're storing a function ref, emit a FunctionDef instead of an Assign
            if isinstance(value, _FunctionRef):
                fn = _function_def_from_ref(value, ins.argval)
                self.body.append(fn)
                return i + 1
            # If we're storing a class ref, emit a ClassDef
            if isinstance(value, _ClassRef):
                cls = _class_def_from_ref(value, ins.argval)
                if getattr(value, "decorators", None):
                    cls.decorator_list = list(value.decorators) + cls.decorator_list
                self.body.append(cls)
                return i + 1
            target = _name(ins.argval)
            target.ctx = ast.Store()
            self.body.append(ast.Assign(targets=[target], value=value))
            return i + 1
        if op == "STORE_FAST_STORE_FAST":
            if isinstance(ins.argval, tuple):
                a, b = ins.argval
            else:
                a, b = ins.argrepr.split(",")
                a = a.strip(); b = b.strip()
            # Stack: ..., v_b, v_a
            v_a = self.stack.pop()
            v_b = self.stack.pop()
            self.body.append(ast.Assign(targets=[_store_name(a)], value=v_a))
            self.body.append(ast.Assign(targets=[_store_name(b)], value=v_b))
            return i + 1
        if op == "STORE_ATTR":
            obj = self.stack.pop()
            value = self.stack.pop()
            target = ast.Attribute(value=obj, attr=ins.argval, ctx=ast.Store())
            self.body.append(ast.Assign(targets=[target], value=value))
            return i + 1
        if op == "STORE_SUBSCR":
            idx = self.stack.pop()
            container = self.stack.pop()
            value = self.stack.pop()
            target = ast.Subscript(value=container, slice=idx, ctx=ast.Store())
            self.body.append(ast.Assign(targets=[target], value=value))
            return i + 1
        if op == "DELETE_NAME" or op == "DELETE_FAST" or op == "DELETE_GLOBAL" or op == "DELETE_DEREF":
            target = _name(ins.argval)
            target.ctx = ast.Del()
            self.body.append(ast.Delete(targets=[target]))
            return i + 1
        if op == "DELETE_ATTR":
            obj = self.stack.pop()
            target = ast.Attribute(value=obj, attr=ins.argval, ctx=ast.Del())
            self.body.append(ast.Delete(targets=[target]))
            return i + 1
        if op == "DELETE_SUBSCR":
            idx = self.stack.pop()
            container = self.stack.pop()
            target = ast.Subscript(value=container, slice=idx, ctx=ast.Del())
            self.body.append(ast.Delete(targets=[target]))
            return i + 1

        # ---- POPs ----
        if op == "POP_TOP":
            if not self.stack:
                return i + 1
            v = self.stack.pop()
            if isinstance(v, _CodeObj):
                return i + 1
            if isinstance(v, _ImportRef):
                # Discarded import reference (after all IMPORT_FROM names are
                # extracted via STORE_NAME). The actual `from X import a, b, c`
                # statement is the concatenation of those STORE_NAMEs — but our
                # naive emitter has already emitted one ImportFrom per name.
                # Coalesce in a post-process if desired.
                return i + 1
            self.body.append(ast.Expr(value=v))
            return i + 1
        if op == "POP_EXCEPT":
            return i + 1
        if op == "NOP":
            return i + 1
        if op == "EXTENDED_ARG":
            # Already handled by dis (the extended arg is folded into the next instr).
            return i + 1
        if op == "RERAISE":
            self.body.append(ast.Raise(exc=None, cause=None))
            return i + 1
        if op == "RAISE_VARARGS":
            if arg == 0:
                self.body.append(ast.Raise(exc=None, cause=None))
            elif arg == 1:
                exc = self.stack.pop()
                self.body.append(ast.Raise(exc=exc, cause=None))
            else:
                cause = self.stack.pop()
                exc = self.stack.pop()
                self.body.append(ast.Raise(exc=exc, cause=cause))
            return i + 1

        # ---- Function build ----
        if op == "MAKE_FUNCTION":
            tos = self.stack.pop()
            assert isinstance(tos, _CodeObj), f"MAKE_FUNCTION expects code obj, got {tos}"
            code = tos.code
            # If this is a comprehension/generator-expression code object (one
            # implicit arg `.0`), and we're about to receive an iter from a
            # following CALL 0, treat it as a comprehension that we will
            # synthesize from the inner code structure.
            if _is_comprehension_code(code):
                self.stack.append(_ComprehensionRef(code))
            else:
                self.stack.append(_FunctionRef(code))
            return i + 1
        if op == "SET_FUNCTION_ATTRIBUTE":
            # 3.13+: stack is [..., value, fn]. Pop fn, pop value, set attr, push fn.
            # arg is a bitflag of which attribute is being set. 0x01: defaults,
            # 0x02: kwdefaults, 0x04: annotations, 0x08: closure
            fref = self.stack.pop()
            value = self.stack.pop()
            # Accept both _FunctionRef and _ComprehensionRef (the latter is a genexpr
            # code object that may also have closures attached in round 11).
            if not isinstance(fref, (_FunctionRef, _ComprehensionRef)):
                raise AssertionError(
                    f"SET_FUNCTION_ATTRIBUTE expects _FunctionRef, got {type(fref).__name__}")
            if arg & 0x01:
                fref.defaults = value
            if arg & 0x02:
                fref.kw_defaults = value
            if arg & 0x04:
                fref.annotations = value
            if arg & 0x08:
                fref.closure = value
            self.stack.append(fref)
            return i + 1

        # ---- Binary / unary ops ----
        if op == "BINARY_OP":
            op_idx = arg
            right = self.stack.pop()
            left = self.stack.pop()
            spec = BINOP_MAP.get(op_idx)
            if spec == "subscr":
                self.stack.append(ast.Subscript(value=left, slice=right, ctx=ast.Load()))
            elif spec is not None:
                self.stack.append(ast.BinOp(left=left, op=spec, right=right))
            else:
                raise NotImplementedError(f"BINARY_OP arg {op_idx}")
            return i + 1
        if op == "BINARY_SUBSCR":
            idx = self.stack.pop()
            container = self.stack.pop()
            self.stack.append(ast.Subscript(value=container, slice=idx, ctx=ast.Load()))
            return i + 1
        if op == "BINARY_SLICE":
            stop = self.stack.pop()
            start = self.stack.pop()
            container = self.stack.pop()
            self.stack.append(ast.Subscript(
                value=container,
                slice=ast.Slice(lower=start, upper=stop, step=None),
                ctx=ast.Load(),
            ))
            return i + 1
        if op == "STORE_SLICE":
            stop = self.stack.pop()
            start = self.stack.pop()
            container = self.stack.pop()
            value = self.stack.pop()
            self.body.append(ast.Assign(
                targets=[ast.Subscript(
                    value=container,
                    slice=ast.Slice(lower=start, upper=stop, step=None),
                    ctx=ast.Store(),
                )],
                value=value,
            ))
            return i + 1
        if op == "UNARY_NEGATIVE":
            v = self.stack.pop()
            if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)):
                self.stack.append(_const(-v.value))
            else:
                self.stack.append(ast.UnaryOp(op=ast.USub(), operand=v))
            return i + 1
        if op == "UNARY_NOT" or op == "TO_BOOL_NOT":
            v = self.stack.pop()
            self.stack.append(ast.UnaryOp(op=ast.Not(), operand=v))
            return i + 1
        if op == "UNARY_INVERT":
            v = self.stack.pop()
            self.stack.append(ast.UnaryOp(op=ast.Invert(), operand=v))
            return i + 1
        if op == "TO_BOOL":
            # No semantic change at AST level
            return i + 1
        if op == "FORMAT_VALUE":
            v = self.stack.pop()
            arg_val = arg if isinstance(arg, int) else 0
            conv = arg_val & 0x03
            has_spec = bool(arg_val & 0x04)
            spec = self.stack.pop() if has_spec else None
            conv_map = {0: -1, 1: 115, 2: 114, 3: 97}
            self.stack.append(ast.FormattedValue(
                value=v,
                conversion=conv_map.get(conv, -1),
                format_spec=spec,
            ))
            return i + 1
        if op == "FORMAT_SIMPLE":
            v = self.stack.pop()
            self.stack.append(ast.FormattedValue(value=v, conversion=-1, format_spec=None))
            return i + 1
        if op == "FORMAT_WITH_SPEC":
            spec = self.stack.pop()
            v = self.stack.pop()
            self.stack.append(ast.FormattedValue(value=v, conversion=-1, format_spec=spec))
            return i + 1
        if op == "CONVERT_VALUE":
            # arg = 1 (str), 2 (repr), 3 (ascii)
            conv_map = {1: 115, 2: 114, 3: 97}
            v = self.stack.pop()
            self.stack.append(ast.FormattedValue(
                value=v, conversion=conv_map.get(arg, -1), format_spec=None))
            return i + 1
        if op == "BUILD_STRING":
            count = arg
            parts = self.stack[-count:]
            del self.stack[-count:]
            # Promote bare ast.Constant str to part too
            self.stack.append(ast.JoinedStr(values=parts))
            return i + 1

        # ---- Compare ops ----
        if op == "COMPARE_OP":
            right = self.stack.pop()
            left = self.stack.pop()
            cmp_str = _normalize_compare_op(ins.argrepr)
            ast_cmp = COMPARE_OPS.get(cmp_str)
            if ast_cmp is None:
                raise NotImplementedError(f"COMPARE_OP {cmp_str!r}")
            self.stack.append(ast.Compare(left=left, ops=[ast_cmp], comparators=[right]))
            return i + 1
        if op == "IS_OP":
            right = self.stack.pop()
            left = self.stack.pop()
            op_ = ast.IsNot() if arg == 1 else ast.Is()
            self.stack.append(ast.Compare(left=left, ops=[op_], comparators=[right]))
            return i + 1
        if op == "CONTAINS_OP":
            right = self.stack.pop()
            left = self.stack.pop()
            op_ = ast.NotIn() if arg == 1 else ast.In()
            self.stack.append(ast.Compare(left=left, ops=[op_], comparators=[right]))
            return i + 1

        # ---- Container builders ----
        if op == "BUILD_TUPLE":
            count = arg
            elts = self.stack[-count:] if count else []
            if count:
                del self.stack[-count:]
            self.stack.append(ast.Tuple(elts=elts, ctx=ast.Load()))
            return i + 1
        if op == "BUILD_LIST":
            count = arg
            elts = self.stack[-count:] if count else []
            if count:
                del self.stack[-count:]
            self.stack.append(ast.List(elts=elts, ctx=ast.Load()))
            return i + 1
        if op == "BUILD_SET":
            count = arg
            elts = self.stack[-count:] if count else []
            if count:
                del self.stack[-count:]
            if not elts:
                # empty set isn't expressible as {} — use set()
                self.stack.append(ast.Call(func=_name("set"), args=[], keywords=[]))
            else:
                self.stack.append(ast.Set(elts=elts))
            return i + 1
        if op == "BUILD_MAP":
            count = arg
            keys = []
            values = []
            for _ in range(count):
                v = self.stack.pop()
                k = self.stack.pop()
                keys.insert(0, k)
                values.insert(0, v)
            self.stack.append(ast.Dict(keys=keys, values=values))
            return i + 1
        if op == "BUILD_CONST_KEY_MAP":
            count = arg
            keys_tuple = self.stack.pop()
            assert isinstance(keys_tuple, ast.Constant)
            key_vals = list(keys_tuple.value)
            values = self.stack[-count:]
            del self.stack[-count:]
            keys = [_const(k) for k in key_vals]
            self.stack.append(ast.Dict(keys=keys, values=values))
            return i + 1
        if op == "BUILD_SLICE":
            if arg == 3:
                step = self.stack.pop()
                stop = self.stack.pop()
                start = self.stack.pop()
            else:
                step = None
                stop = self.stack.pop()
                start = self.stack.pop()
            # convert None constants to None
            def _slice_part(p):
                if isinstance(p, ast.Constant) and p.value is None:
                    return None
                return p
            self.stack.append(ast.Slice(
                lower=_slice_part(start),
                upper=_slice_part(stop),
                step=_slice_part(step) if step is not None else None,
            ))
            return i + 1
        if op == "LIST_EXTEND" or op == "LIST_APPEND":
            v = self.stack.pop()
            target_lst = self.stack[-arg]
            # For LIST_EXTEND, v is a tuple/list/iterable that should expand into target.
            # For our purposes — produced by ast.unparse output of `[a, *b]` patterns —
            # we represent it as a Starred element.
            if op == "LIST_EXTEND":
                if isinstance(v, ast.Tuple):
                    target_lst.elts.extend(v.elts)
                else:
                    target_lst.elts.append(ast.Starred(value=v, ctx=ast.Load()))
            else:
                target_lst.elts.append(v)
            return i + 1
        if op == "SET_ADD":
            v = self.stack.pop()
            target_set = self.stack[-arg]
            target_set.elts.append(v)
            return i + 1
        if op == "SET_UPDATE":
            v = self.stack.pop()
            target_set = self.stack[-arg]
            target_set.elts.append(ast.Starred(value=v, ctx=ast.Load()))
            return i + 1
        if op == "MAP_ADD":
            v = self.stack.pop()
            k = self.stack.pop()
            target_map = self.stack[-arg]
            target_map.keys.append(k)
            target_map.values.append(v)
            return i + 1
        if op == "DICT_UPDATE" or op == "DICT_MERGE":
            v = self.stack.pop()
            target_dict = self.stack[-arg]
            target_dict.keys.append(None)
            target_dict.values.append(v)
            return i + 1
        if op == "LIST_TO_TUPLE":
            lst = self.stack.pop()
            self.stack.append(ast.Tuple(elts=lst.elts, ctx=ast.Load()))
            return i + 1

        # ---- Calls ----
        if op == "CALL":
            argc = arg
            # Stack layout: [..., callable, self_or_null, arg0, ..., argN-1]
            # Total consumed: argc + 2.
            slice_args = self.stack[-argc:] if argc else []
            if argc:
                del self.stack[-argc:]
            self_or_null = self.stack.pop()
            callable_ = self.stack.pop()

            # Handle __build_class__ — produces a class definition
            if isinstance(callable_, _BuildClassMarker) or \
                    isinstance(self_or_null, _BuildClassMarker):
                # Args are [class_body_fn, name, *bases]; we get them as slice_args.
                if isinstance(callable_, _BuildClassMarker):
                    actual_args = ([self_or_null] if not isinstance(self_or_null, _NullMarker) else []) + slice_args
                else:
                    actual_args = slice_args
                if actual_args:
                    class_fn = actual_args[0]
                    class_name = (
                        actual_args[1].value
                        if len(actual_args) > 1 and isinstance(actual_args[1], ast.Constant)
                        else "<unnamed_class>"
                    )
                    bases = actual_args[2:]
                    self.stack.append(_ClassRef(class_fn.code if isinstance(class_fn, _FunctionRef) else None,
                                                 class_name, bases))
                else:
                    self.stack.append(_const(None))
                return i + 1

            # Handle decorator wrapper around _ClassRef: dataclass(_ClassRef)
            if isinstance(self_or_null, _ClassRef) and argc == 0:
                # callable_(self_or_null) -> wrap _ClassRef in decorators list
                self_or_null.decorators = getattr(self_or_null, "decorators", []) + [callable_]
                self.stack.append(self_or_null)
                return i + 1
            if any(isinstance(a, _ClassRef) for a in slice_args):
                # Some uncommon case
                cls_arg = next(a for a in slice_args if isinstance(a, _ClassRef))
                cls_arg.decorators = getattr(cls_arg, "decorators", []) + [callable_]
                self.stack.append(cls_arg)
                return i + 1

            # Handle comprehension as the callable (genexp/listcomp/etc.):
            if isinstance(callable_, _ComprehensionRef) and argc == 0 \
                    and not isinstance(self_or_null, _NullMarker):
                outer_iter = self_or_null
                fv_map = getattr(self, '_freevar_resolver', None)
                if fv_map is not None:
                    fv_rename = fv_map.get_mapping_for_code(callable_.code)
                else:
                    fv_rename = {}
                comp_node = _build_comprehension(callable_.code, outer_iter,
                                                  freevar_map=fv_rename)
                self.stack.append(comp_node)
                return i + 1

            # Regular call: build the positional args list. If self_or_null is NOT a
            # NULL marker, it counts as the first positional arg (this is the
            # bound-method ABI used after LOAD_ATTR/LOAD_GLOBAL with method shape).
            pos_args = []
            if not isinstance(self_or_null, _NullMarker):
                pos_args.append(self_or_null)
            pos_args.extend(slice_args)
            # Convert any _FunctionRef args into a Lambda expression
            _fv_res = getattr(self, '_freevar_resolver', None)
            def _maybe_lambda(a):
                if not isinstance(a, _FunctionRef):
                    return a
                fm = _fv_res.get_mapping_for_code(a.code) if _fv_res else {}
                return _fref_to_lambda(a, freevar_map=fm)
            pos_args = [_maybe_lambda(a) for a in pos_args]

            # If callable_ is itself an attribute access where self == pos_args[0],
            # collapse to method call (a.b(c) instead of a.b(a, c)).
            if (isinstance(callable_, ast.Attribute) and pos_args
                    and _is_same_expr(callable_.value, pos_args[0])):
                pos_args = pos_args[1:]

            if isinstance(callable_, _FunctionRef):
                func_expr = _expr_of(callable_)
            else:
                func_expr = callable_

            args, keywords = _split_args_keywords(pos_args)
            self.stack.append(ast.Call(func=func_expr, args=args, keywords=keywords))
            return i + 1
        if op == "CALL_FUNCTION_EX":
            kwargs = None
            if arg & 0x01:
                kwargs = self.stack.pop()
            args_tuple = self.stack.pop()
            func = self.stack.pop()
            # args_tuple is a Tuple/List or a Call(list(...)) — represent as *args
            call_args = []
            if isinstance(args_tuple, ast.Tuple) or isinstance(args_tuple, ast.List):
                call_args = list(args_tuple.elts)
            else:
                call_args = [ast.Starred(value=args_tuple, ctx=ast.Load())]
            keywords = []
            if kwargs is not None:
                if isinstance(kwargs, ast.Dict):
                    for k, v in zip(kwargs.keys, kwargs.values):
                        if k is None:
                            keywords.append(ast.keyword(arg=None, value=v))
                        elif isinstance(k, ast.Constant) and isinstance(k.value, str):
                            keywords.append(ast.keyword(arg=k.value, value=v))
                        else:
                            keywords.append(ast.keyword(arg=None, value=v))
                else:
                    keywords.append(ast.keyword(arg=None, value=kwargs))
            self.stack.append(ast.Call(func=func, args=call_args, keywords=keywords))
            return i + 1
        if op == "KW_NAMES":
            self._kw_names = ins.argval
            return i + 1
        if op == "CALL_KW":
            argc = arg
            kwnames_const = self.stack.pop()
            assert isinstance(kwnames_const, ast.Constant) and isinstance(kwnames_const.value, tuple), \
                f"CALL_KW expects a tuple of kw names on TOS, got {kwnames_const}"
            kw_names = kwnames_const.value
            n_kw = len(kw_names)
            kw_values = self.stack[-n_kw:]
            del self.stack[-n_kw:]
            n_pos = argc - n_kw
            pos_args = self.stack[-n_pos:] if n_pos else []
            if n_pos:
                del self.stack[-n_pos:]
            self_or_null = self.stack.pop()
            callable_ = self.stack.pop()
            all_pos = []
            if not isinstance(self_or_null, _NullMarker):
                all_pos.append(self_or_null)
            all_pos.extend(pos_args)
            # Method-call collapse
            if (isinstance(callable_, ast.Attribute) and all_pos
                    and _is_same_expr(callable_.value, all_pos[0])):
                all_pos = all_pos[1:]
            _fv_res2 = getattr(self, '_freevar_resolver', None)
            def _maybe_lambda2(a):
                if not isinstance(a, _FunctionRef):
                    return a
                fm = _fv_res2.get_mapping_for_code(a.code) if _fv_res2 else {}
                return _fref_to_lambda(a, freevar_map=fm)
            all_pos = [_maybe_lambda2(a) for a in all_pos]
            kw_values = [_maybe_lambda2(a) for a in kw_values]
            keywords = [ast.keyword(arg=name, value=value)
                        for name, value in zip(kw_names, kw_values)]
            self.stack.append(ast.Call(func=callable_, args=all_pos, keywords=keywords))
            return i + 1

        # ---- Iteration / yield ----
        if op == "GET_ITER":
            # Check if the next instruction begins the inline-comprehension pattern
            # (`LOAD_FAST_AND_CLEAR <accum> ; SWAP 2 ; BUILD_LIST/SET/MAP 0 ; SWAP 2 ; FOR_ITER`).
            j = i + 1
            while j < len(self.instructions) and self.instructions[j].opname in (
                    "CACHE", "NOP"):
                j += 1
            if j < len(self.instructions) and self.instructions[j].opname == "LOAD_FAST_AND_CLEAR":
                result = self._try_inline_comp(j, len(self.instructions), None)
                if result is not None:
                    return result
            return i + 1
        if op == "GET_AWAITABLE":
            return i + 1
        if op == "YIELD_VALUE":
            v = self.stack.pop()
            self.stack.append(ast.Yield(value=v))
            return i + 1
        if op == "JUMP_FORWARD":
            return i + 1  # handled at higher level
        if op == "CALL_INTRINSIC_1":
            # arg 0 = INVALID, see Include/internal/pycore_intrinsics.h
            # For generator wrappers (3, RETURN_GENERATOR-related) we just no-op.
            # Common ones we encounter: INTRINSIC_STOPITERATION_ERROR (4),
            # INTRINSIC_LIST_TO_TUPLE (1), INTRINSIC_UNARY_POSITIVE (2)
            if ins.argrepr == "INTRINSIC_LIST_TO_TUPLE":
                v = self.stack.pop()
                if isinstance(v, ast.List):
                    self.stack.append(ast.Tuple(elts=v.elts, ctx=ast.Load()))
                else:
                    self.stack.append(ast.Tuple(elts=[ast.Starred(value=v, ctx=ast.Load())], ctx=ast.Load()))
            elif ins.argrepr == "INTRINSIC_UNARY_POSITIVE":
                v = self.stack.pop()
                self.stack.append(ast.UnaryOp(op=ast.UAdd(), operand=v))
            else:
                # ignore
                pass
            return i + 1
        if op == "CALL_INTRINSIC_2":
            return i + 1
        if op == "SEND" or op == "SEND_GEN":
            return i + 1

        # ---- Misc ----
        if op == "COPY":
            self.stack.append(self.stack[-arg])
            return i + 1
        if op == "SWAP":
            a = -1
            b = -arg
            self.stack[a], self.stack[b] = self.stack[b], self.stack[a]
            return i + 1
        if op == "DUP_TOP":
            self.stack.append(self.stack[-1])
            return i + 1
        if op == "UNPACK_SEQUENCE":
            # Stack TOS is an iterable being unpacked into <arg> targets via following STORE_* ops.
            v = self.stack.pop()
            # Push <arg> sentinels marking we need to unpack.
            self.stack.append(_UnpackMarker(v, arg))
            for k in range(arg):
                self.stack.append(_UnpackElt(v, arg - k - 1))
            return i + 1
        if op == "UNPACK_EX":
            # Similar but with one starred target
            v = self.stack.pop()
            before = arg & 0xFF
            after = (arg >> 8) & 0xFF
            self.stack.append(_UnpackEx(v, before, after))
            return i + 1
        if op == "PUSH_EXC_INFO":
            self.stack.append(_const(None))
            return i + 1
        if op == "CHECK_EXC_MATCH":
            return i + 1
        if op == "CHECK_EG_MATCH":
            return i + 1
        if op == "CLEANUP_THROW":
            return i + 1
        if op == "BEFORE_ASYNC_WITH" or op == "BEFORE_WITH":
            mgr = self.stack.pop()
            self.stack.append(_WithMarker(mgr))
            self.stack.append(_WithEnter(mgr))
            return i + 1

        if op == "LOAD_SPECIAL":
            # 0 = __enter__, 1 = __exit__
            # Stack: [..., cm] → [..., cm, attr]  for arg=0 (push __enter__ then NULL)
            #                 → [..., __exit__, cm] for arg=1 (used by with)
            # We don't fully model these — emit placeholders. The with-statement is
            # detected at a higher level.
            if arg == 1:
                # leave the manager in place; push a sentinel for the __exit__ slot
                self.stack.append(_WithExitMarker(self.stack[-1] if self.stack else None))
            else:
                # __enter__: replace TOS with the call result placeholder
                cm = self.stack[-1] if self.stack else None
                self.stack.append(_WithEnterMarker(cm))
            return i + 1
        if op == "RESUME_CHECK":
            return i + 1
        if op == "EXIT_INIT_CHECK":
            return i + 1
        if op == "INTERPRETER_EXIT":
            return i + 1

        if op == "IMPORT_NAME":
            # Stack: fromlist, level
            fromlist = self.stack.pop()
            level = self.stack.pop()
            level_val = level.value if isinstance(level, ast.Constant) else 0
            from_names = []
            if isinstance(fromlist, ast.Constant) and isinstance(fromlist.value, tuple):
                from_names = list(fromlist.value)
            elif isinstance(fromlist, ast.Constant) and fromlist.value is None:
                from_names = None
            mod_name = ins.argval
            self.stack.append(_ImportRef(mod_name, level_val, from_names))
            return i + 1
        if op == "IMPORT_FROM":
            # Stack TOS: an _ImportRef; we push the attribute name reference
            mod_ref = self.stack[-1]
            self.stack.append(_ImportFromAttr(mod_ref, ins.argval))
            return i + 1
        if op == "IMPORT_STAR":
            mod = self.stack.pop()
            mod_name = mod.module if isinstance(mod, _ImportRef) else "<?>"
            self.body.append(ast.ImportFrom(module=mod_name, names=[ast.alias(name="*")], level=0))
            return i + 1

        raise NotImplementedError(f"op {op} at offset {ins.offset}")

    # ------------------------------------------------------------------
    # FOR loop: build ast.For
    # ------------------------------------------------------------------
    def _for_loop(self, i, end):
        ins = self.instructions[i]
        assert ins.opname == "FOR_ITER"
        iter_expr = self.stack.pop()
        # Body starts at i+1, ends just before JUMP_BACKWARD whose target == ins.offset
        # FOR_ITER's argval is the offset after the loop end (where END_FOR is).
        loop_end_offset = ins.argval
        # find next index
        loop_end_idx = self.idx_for_offset[loop_end_offset]

        # The first instruction of the body usually stores the loop var.
        # We start a recursive decompiler for the body.
        # First: capture the loop variable from STORE_FAST / STORE_NAME / UNPACK_SEQUENCE
        j = i + 1
        # Skip NOT_TAKEN, RESUME, NOP
        while j < loop_end_idx and self.instructions[j].opname in (
                "NOT_TAKEN", "NOP", "RESUME", "CACHE"):
            j += 1
        # Recursive sub-decompiler for body
        sub = _SubDecompiler(self)
        # First parse the storage of the loop var(s)
        target = _consume_for_target(sub, self, j)
        j = sub._next_idx
        # Now decompile body until just before JUMP_BACKWARD to FOR_ITER offset
        # Body ends with a JUMP_BACKWARD whose argval == ins.offset
        body_stmts, j = _decompile_segment(sub, self, j, loop_end_idx,
                                            backjump_offset=ins.offset)
        # After body we are at JUMP_BACKWARD; skip it
        if j < len(self.instructions) and self.instructions[j].opname.startswith("JUMP_BACKWARD"):
            j += 1
        # Then loop_end_offset / loop_end_idx points to END_FOR / POP_ITER
        # Skip END_FOR, POP_ITER, optional POP_TOP
        while j < len(self.instructions) and self.instructions[j].opname in (
                "END_FOR", "POP_ITER", "POP_BLOCK"):
            j += 1
        self.body.append(ast.For(
            target=target,
            iter=iter_expr,
            body=body_stmts if body_stmts else [ast.Pass()],
            orelse=[],
        ))
        return j

    # ------------------------------------------------------------------
    # if/else: simple POP_JUMP_IF_X branching
    # ------------------------------------------------------------------
    def _if_else(self, i, end):
        ins = self.instructions[i]
        op = ins.opname
        target_offset = ins.argval
        target_idx = self.idx_for_offset.get(target_offset, end)

        # Check whether this is the test of a `while` loop. The body (between i
        # and target_idx) should end with a JUMP_BACKWARD whose target is the
        # start of this condition's evaluation. We approximate by looking for a
        # JUMP_BACKWARD at the very end of the [i+1, target_idx) range whose
        # target is exactly the start of this basic block.
        cond_offset_floor = self._find_cond_start(i)
        # The terminal jump should be the LAST instruction in the body just before target_idx
        # (sometimes preceded by NOT_TAKEN cleanup). Walk back from target_idx-1.
        k_back = target_idx - 1
        while k_back > i and self.instructions[k_back].opname in (
                "NOT_TAKEN", "NOP", "CACHE"):
            k_back -= 1
        if k_back > i:
            jb_ins = self.instructions[k_back]
            if jb_ins.opname.startswith("JUMP_BACKWARD") \
                    and jb_ins.argval == cond_offset_floor:
                return self._while_loop(i, k_back, target_idx, op, end)

        # Detect `<a> or <b>` / `<a> and <b>` short-circuit pattern:
        #   <a> COPY 1 TO_BOOL POP_JUMP_IF_TRUE/FALSE L1 POP_TOP <b> L1: <use TOS>
        if i >= 2 and self.instructions[i-1].opname in ("TO_BOOL", "TO_BOOL_NOT") \
                and self.instructions[i-2].opname == "COPY" \
                and self.instructions[i-2].arg == 1 \
                and self.stack:
            cond = self.stack.pop()
            j = i + 1
            while j < end and self.instructions[j].opname == "NOT_TAKEN":
                j += 1
            if j < end and self.instructions[j].opname == "POP_TOP":
                if self.stack and _is_same_expr(self.stack[-1], cond):
                    self.stack.pop()
                j += 1
                target_idx_local = target_idx
                sub = _SubDecompiler(self)
                _, j_after = _decompile_segment(sub, self, j, target_idx_local)
                alt = self.stack.pop() if self.stack else _name("__alt__")
                bool_op = ast.Or() if op == "POP_JUMP_IF_TRUE" else ast.And()
                self.stack.append(ast.BoolOp(op=bool_op, values=[cond, alt]))
                return j_after
            # Pattern didn't match — put the cond back
            self.stack.append(cond)

        # Pop condition
        if not self.stack:
            # Some upstream issue — emit a placeholder for the condition
            cond = _name("__missing_cond__")
        else:
            cond = self.stack.pop()

        # Invert per opname
        invert = False
        if op == "POP_JUMP_IF_FALSE":
            invert = False
        elif op == "POP_JUMP_IF_TRUE":
            invert = True
        elif op == "POP_JUMP_IF_NONE":
            cond = ast.Compare(left=cond, ops=[ast.Is()], comparators=[_const(None)])
            invert = True
        elif op == "POP_JUMP_IF_NOT_NONE":
            cond = ast.Compare(left=cond, ops=[ast.IsNot()], comparators=[_const(None)])
            invert = True

        # Skip NOT_TAKEN
        j = i + 1
        while j < end and self.instructions[j].opname == "NOT_TAKEN":
            j += 1

        # Check for the "skip" pattern: POP_JUMP_IF_X target ; JUMP_BACKWARD <loop>
        # which means "if <cond>: go to body at target; else: continue loop".
        # The body is at the target. We represent this as `if invert_op(cond): body`.
        #
        # Guard: if target_idx == end, the "body" is actually the outer context's
        # continuation (we're nested inside another _if_else and the JUMP_BACKWARD
        # plus outer else both point to the same L). In that case, emit a `continue`
        # for the JUMP_BACKWARD and let the outer context handle the body at target.
        if j < end and self.instructions[j].opname.startswith("JUMP_BACKWARD"):
            jb_offset = self.instructions[j].argval
            if target_idx >= end:
                # The if-body target is outside our range — just emit `continue`
                # for the JUMP_BACKWARD and stop. The outer context handles the target.
                test = cond
                if op == "POP_JUMP_IF_FALSE":
                    test = ast.UnaryOp(op=ast.Not(), operand=cond)
                elif op == "POP_JUMP_IF_NONE":
                    test = ast.Compare(left=cond.left, ops=[ast.Is()],
                                        comparators=cond.comparators)
                elif op == "POP_JUMP_IF_NOT_NONE":
                    test = ast.Compare(left=cond.left, ops=[ast.IsNot()],
                                        comparators=cond.comparators)
                # Invert again: POP_JUMP_IF_FALSE means "if False, goto target (skip body)"
                # so the JUMP_BACKWARD runs when condition is True. For "continue", we want
                # `if condition: continue` but we've already inverted above for POP_JUMP_IF_FALSE.
                # Let's re-think: POP_JUMP_IF_FALSE with JUMP_BACKWARD:
                #   condition True → fall through to JUMP_BACKWARD → continue
                #   condition False → jump to target (outside our range)
                # So: `if condition: continue` (no inversion for POP_JUMP_IF_FALSE).
                # Recompute without inversion:
                if op == "POP_JUMP_IF_FALSE":
                    cond_for_continue = cond
                elif op == "POP_JUMP_IF_TRUE":
                    cond_for_continue = ast.UnaryOp(op=ast.Not(), operand=cond)
                else:
                    cond_for_continue = test  # already set above
                self.body.append(ast.If(
                    test=cond_for_continue,
                    body=[ast.Continue()],
                    orelse=[],
                ))
                return j + 1  # advance past the JUMP_BACKWARD

            # Build the "if" with body at `target_idx`, ending at the next JUMP_BACKWARD
            # from inside that body. We find the second JUMP_BACKWARD that targets jb_offset.
            body_start = target_idx
            body_end = end
            # Find the JUMP_BACKWARD from inside the if-body that ties back to the same loop
            for k in range(body_start, end):
                k_ins = self.instructions[k]
                if k_ins.opname.startswith("JUMP_BACKWARD") and k_ins.argval == jb_offset:
                    body_end = k
                    break
            sub = _SubDecompiler(self)
            body_stmts, _ = _decompile_segment(sub, self, body_start, body_end,
                                                backjump_offset=jb_offset)
            # NB: we did NOT invert here because the jump-target IS the body. For
            # POP_JUMP_IF_TRUE, true → goto body, so condition is unnegated; for
            # POP_JUMP_IF_FALSE, false → goto body, so condition needs negation.
            test = cond
            if op == "POP_JUMP_IF_FALSE":
                test = ast.UnaryOp(op=ast.Not(), operand=cond)
            elif op == "POP_JUMP_IF_NONE":
                # already negated above to is-None; here body runs when condition is None
                # so use the original: x is None
                test = ast.Compare(left=cond.left, ops=[ast.Is()],
                                    comparators=cond.comparators)
            elif op == "POP_JUMP_IF_NOT_NONE":
                test = ast.Compare(left=cond.left, ops=[ast.IsNot()],
                                    comparators=cond.comparators)
            self.body.append(ast.If(test=test,
                                    body=body_stmts if body_stmts else [ast.Pass()],
                                    orelse=[]))
            # Advance past the body's terminating JUMP_BACKWARD so we don't reprocess it.
            return body_end + 1

        # Try ternary expression: POP_JUMP_IF + <expr> + JUMP_FORWARD + <expr>
        # where both expressions leave one value on the stack. We detect by
        # snapshotting the stack height: if the value-branch leaves height+1
        # at the JUMP_FORWARD, and the else-branch also leaves height+1 at
        # the convergence point, we synthesize an IfExp.
        stack_height = len(self.stack)
        ternary_result = self._try_ternary(j, target_idx, target_offset, cond, op, end)
        if ternary_result is not None:
            return ternary_result

        # Default: true branch is fall-through, else branch (if any) at target.
        # Save a snapshot of the stack before the true branch so we can restore it
        # for the else branch (both branches start from the same pre-condition stack).
        stack_snapshot = list(self.stack)
        sub = _SubDecompiler(self)
        true_stmts, j_after = _decompile_segment(sub, self, j, target_idx,
                                                  backjump_offset=None,
                                                  stop_on_forward_past=target_offset)
        # If j_after is JUMP_FORWARD, this is the if/else split point
        else_stmts = []
        if (j_after < end
                and self.instructions[j_after].opname in ("JUMP_FORWARD",)):
            after_offset = self.instructions[j_after].argval
            j_after += 1
            after_idx = self.idx_for_offset[after_offset]
            # Restore stack to pre-branch state so else branch starts cleanly.
            self.stack[:] = stack_snapshot
            sub2 = _SubDecompiler(self)
            else_stmts, j_after = _decompile_segment(sub2, self, j_after, after_idx)
        elif (j_after < end
                and self.instructions[j_after].opname.startswith("JUMP_BACKWARD")):
            # Both branches end with the same JUMP_BACKWARD (loop continuation): the
            # else branch starts at target_idx and also ends with JUMP_BACKWARD to
            # the same target. Decompile it.
            jb_offset = self.instructions[j_after].argval
            # else branch from target_idx to its own JUMP_BACKWARD
            else_start = target_idx
            else_end = end
            for k in range(else_start, end):
                k_ins = self.instructions[k]
                if k_ins.opname.startswith("JUMP_BACKWARD") and k_ins.argval == jb_offset:
                    else_end = k
                    break
            self.stack[:] = stack_snapshot
            sub2 = _SubDecompiler(self)
            else_stmts, _ = _decompile_segment(sub2, self, else_start, else_end + 1,
                                                backjump_offset=jb_offset)
            # Advance past the else branch's JUMP_BACKWARD
            j_after = else_end + 1
        # After the if/else, the stack state is whatever the branches produced.
        # If both branches leave the same result, the parent stack reflects that.
        test = cond
        if invert:
            test = ast.UnaryOp(op=ast.Not(), operand=cond)
        self.body.append(ast.If(test=test, body=true_stmts if true_stmts else [ast.Pass()],
                                orelse=else_stmts))
        return j_after

    def _with_stmt(self, i, end):
        """Build a `with <cm> as <name>:` block from the bytecode pattern starting
        at COPY 1 ; LOAD_SPECIAL 1 (__exit__) ; SWAP 2 ; SWAP 3 ; LOAD_SPECIAL 0 (__enter__) ;
        CALL 0 ; STORE_* <name> ; <body> ; LOAD_CONST None * 3 ; CALL 3 ; POP_TOP ;
        JUMP_FORWARD <after-with>.
        """
        ins = self.instructions
        # The CM expr is on the stack. Pop it.
        cm = self.stack.pop() if self.stack else _name("__cm__")
        # Skip: COPY 1, LOAD_SPECIAL 1, SWAP 2, SWAP 3, LOAD_SPECIAL 0, CALL 0
        j = i + 6
        # Wait — actually the order is COPY, LOAD_SPECIAL 1, SWAP 2, SWAP 3,
        # LOAD_SPECIAL 0, CALL 0 — that's 6 instructions. Let's verify and skip.
        while j < end and ins[j].opname in ("CACHE", "NOP"):
            j += 1
        # Optional STORE for `as <name>`
        as_name = None
        if j < end and ins[j].opname in ("STORE_NAME", "STORE_FAST"):
            as_name = ins[j].argval
            j += 1
        # Now decompile the body until we see LOAD_CONST None (3 times) ; CALL 3 ; POP_TOP ; JUMP_FORWARD
        # Find the closing pattern
        close_idx = None
        for k in range(j, end - 3):
            if ins[k].opname == "LOAD_CONST" and ins[k].argval is None \
                    and ins[k+1].opname == "LOAD_CONST" and ins[k+1].argval is None \
                    and ins[k+2].opname == "LOAD_CONST" and ins[k+2].argval is None:
                close_idx = k
                break
        if close_idx is None:
            close_idx = end
        sub = _SubDecompiler(self)
        body_stmts, _ = _decompile_segment(sub, self, j, close_idx)
        # Skip the closing pattern: LOAD None x3, CALL 3, POP_TOP [, JUMP_FORWARD]
        # Do NOT consume JUMP_FORWARD here — the enclosing _decompile_segment/
        # _if_else machinery needs to see it to detect the else-branch.
        m = close_idx
        # Be lenient about exact form
        while m < end and ins[m].opname in (
                "LOAD_CONST", "CALL", "POP_TOP", "CACHE"):
            m += 1
        # Build the with statement
        item = ast.withitem(
            context_expr=cm,
            optional_vars=_store_name(as_name) if as_name else None,
        )
        self.body.append(ast.With(
            items=[item],
            body=body_stmts if body_stmts else [ast.Pass()],
        ))
        return m

    def _find_cond_start(self, i):
        """Walk backwards from index i to find the start of the basic block
        containing the condition (i.e., the first instruction after the previous
        jump target or basic block boundary). Returns the offset of that instruction.
        """
        # Move back while the preceding instruction is NOT a basic-block boundary
        # and the current instruction is NOT a jump target.
        j = i
        while j > 0:
            jins = self.instructions[j]
            prev = self.instructions[j-1]
            if prev.opname.startswith(("JUMP_", "POP_JUMP_", "RETURN", "FOR_ITER",
                                        "RERAISE", "RAISE")):
                break
            if jins.offset in self.jump_targets:
                break
            j -= 1
        return self.instructions[max(j, 0)].offset

    def _while_loop(self, cond_idx, jb_idx, target_idx, op, end):
        """Build a `while <cond>: <body>` AST from the bytecode pattern:
            <cond_idx>: POP_JUMP_IF_FALSE <target>
            ... <body> ...
            <jb_idx>: JUMP_BACKWARD <cond_block_start>
            <target_idx>: <post-loop>
        Returns the index past target_idx-area (the next instruction after the
        loop block, accounting for follow-on cleanup).
        """
        cond_ins = self.instructions[cond_idx]
        target_offset = cond_ins.argval

        # Pop the condition (still on the stack)
        cond_node = self.stack.pop()
        # Negate based on opname (POP_JUMP_IF_FALSE: body runs when cond is true)
        # — we keep the test as `cond_node` for FALSE branch, since while True: ... ends
        # when the test becomes false; that's the natural while semantic.
        test = cond_node
        if op == "POP_JUMP_IF_TRUE":
            test = ast.UnaryOp(op=ast.Not(), operand=cond_node)
        elif op == "POP_JUMP_IF_NONE":
            test = ast.Compare(left=cond_node.left, ops=[ast.IsNot()],
                                comparators=cond_node.comparators) \
                if isinstance(cond_node, ast.Compare) else \
                ast.Compare(left=cond_node, ops=[ast.IsNot()],
                            comparators=[_const(None)])
        elif op == "POP_JUMP_IF_NOT_NONE":
            test = ast.Compare(left=cond_node, ops=[ast.Is()],
                                comparators=[_const(None)])

        # Decompile body from cond_idx+1 (skip NOT_TAKEN) to jb_idx
        j = cond_idx + 1
        while j < jb_idx and self.instructions[j].opname == "NOT_TAKEN":
            j += 1
        sub = _SubDecompiler(self)
        body_stmts, _ = _decompile_segment(sub, self, j, jb_idx + 1,
                                            backjump_offset=self.instructions[jb_idx].argval)
        self.body.append(ast.While(test=test,
                                    body=body_stmts if body_stmts else [ast.Pass()],
                                    orelse=[]))
        # Return the index past JUMP_BACKWARD. The target_idx is where post-loop
        # code begins.
        return target_idx

    def _try_ternary(self, j, target_idx, target_offset, cond, op, end):
        """If the structure starting at j is a ternary expression
            <true_expr> ; JUMP_FORWARD k ; <else_expr>
        with both branches leaving one stack value, push an IfExp and return the
        next index. Otherwise return None.
        """
        # The "true branch" is from j to target_idx (the POP_JUMP target).
        # The "true branch" should end with JUMP_FORWARD before target_idx.
        # Run a sub-decompile with snapshot stack.
        saved_stack = list(self.stack)
        saved_body = self.body
        self.stack = []
        self.body = []
        try:
            k = j
            while k < target_idx:
                kins = self.instructions[k]
                kop = kins.opname
                if kop == "JUMP_FORWARD":
                    break
                if kop in ("RESUME", "CACHE", "NOT_TAKEN", "NOP"):
                    k += 1
                    continue
                if kop in ("POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE",
                            "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE"):
                    # nested branch — give up on ternary detection
                    self.stack = saved_stack
                    self.body = saved_body
                    return None
                k = self._exec_inst(k)
            # We need exactly 1 value on the stack and a following JUMP_FORWARD.
            if len(self.stack) != 1 or not self.body == []:
                self.stack = saved_stack
                self.body = saved_body
                return None
            if k >= target_idx or self.instructions[k].opname != "JUMP_FORWARD":
                self.stack = saved_stack
                self.body = saved_body
                return None
            true_expr = self.stack[0]
            after_offset = self.instructions[k].argval
            after_idx = self.idx_for_offset[after_offset]
            # Now decompile the else branch from target_idx to after_idx
            self.stack = []
            self.body = []
            m = target_idx
            while m < after_idx:
                mins = self.instructions[m]
                mop = mins.opname
                if mop in ("RESUME", "CACHE", "NOT_TAKEN", "NOP"):
                    m += 1
                    continue
                if mop in ("POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE",
                            "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE"):
                    self.stack = saved_stack
                    self.body = saved_body
                    return None
                m = self._exec_inst(m)
            if len(self.stack) != 1 or self.body:
                self.stack = saved_stack
                self.body = saved_body
                return None
            else_expr = self.stack[0]
            # Build IfExp; restore saved state and push.
            test = cond
            if op == "POP_JUMP_IF_TRUE":
                # true → jump to else_expr means: if cond, return else_expr;
                # if not cond, return true_expr (fall-through)
                test = cond
                ifexp = ast.IfExp(test=test, body=else_expr, orelse=true_expr)
            elif op == "POP_JUMP_IF_FALSE":
                # false → jump to else_expr branch
                ifexp = ast.IfExp(test=cond, body=true_expr, orelse=else_expr)
            elif op == "POP_JUMP_IF_NONE":
                ifexp = ast.IfExp(
                    test=ast.Compare(left=cond.left, ops=[ast.IsNot()],
                                      comparators=cond.comparators),
                    body=true_expr, orelse=else_expr,
                )
            elif op == "POP_JUMP_IF_NOT_NONE":
                ifexp = ast.IfExp(
                    test=ast.Compare(left=cond.left, ops=[ast.Is()],
                                      comparators=cond.comparators),
                    body=true_expr, orelse=else_expr,
                )
            else:
                ifexp = ast.IfExp(test=cond, body=true_expr, orelse=else_expr)
            self.stack = saved_stack
            self.body = saved_body
            self.stack.append(ifexp)
            return m
        except Exception:
            self.stack = saved_stack
            self.body = saved_body
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _NullMarker:
    """Marker for PUSH_NULL. Indicates the self/null slot for the call ABI."""
    pass


class _BuildClassMarker:
    """Marker for LOAD_BUILD_CLASS. We watch for the subsequent CALL that builds a class."""
    pass


class _ClassRef:
    """A class reference produced by __build_class__."""
    def __init__(self, body_code, name, bases):
        self.body_code = body_code
        self.name = name
        self.bases = bases


class _LoadFastAndClearSentinel:
    """Marker for LOAD_FAST_AND_CLEAR, used by inline-comprehension save/restore."""
    def __init__(self, name):
        self.name = name


class _CodeObj:
    """A code object placeholder on the stack (before MAKE_FUNCTION)."""
    def __init__(self, code):
        self.code = code

class _FunctionRef:
    """A function reference placeholder on the stack (after MAKE_FUNCTION)."""
    def __init__(self, code):
        self.code = code
        self.defaults = None
        self.kw_defaults = None
        self.annotations = None
        self.closure = None


class _ComprehensionRef:
    """A comprehension code object placeholder on the stack (after MAKE_FUNCTION
    when the inner code is a comprehension / generator expression)."""
    def __init__(self, code):
        self.code = code
        self.defaults = None
        self.kw_defaults = None
        self.annotations = None
        self.closure = None


def _is_comprehension_code(code):
    """Heuristic: a code object is a comprehension/genexp if its first local is `.0`
    AND it has CO_GENERATOR or returns a single container (listcomp/dictcomp/setcomp).
    """
    if code.co_argcount != 1:
        return False
    if not code.co_varnames or code.co_varnames[0] != ".0":
        return False
    return True


def _apply_name_map(node, name_map):
    """Rename Name nodes in an AST subtree according to name_map dict."""
    if not name_map:
        return node

    class _Renamer(ast.NodeTransformer):
        def visit_Name(self, n):
            if n.id in name_map:
                return ast.copy_location(ast.Name(id=name_map[n.id], ctx=n.ctx), n)
            return n
        def visit_arg(self, n):
            if n.arg in name_map:
                n.arg = name_map[n.arg]
            return n

    return _Renamer().visit(node)


def _build_comprehension(code, outer_iter, freevar_map=None):
    """Reconstruct an ast.GeneratorExp / ListComp / SetComp / DictComp from a
    comprehension code object plus the outer iterable AST node.

    The structure of a generator expression's code is:
        RETURN_GENERATOR; POP_TOP; RESUME 0
        LOAD_FAST .0
        FOR_ITER <end>
        STORE_FAST <var>    (or UNPACK_SEQUENCE + STORE_FAST_STORE_FAST + ...)
        <inner_body building the elt>
        YIELD_VALUE
        RESUME 5; POP_TOP
        JUMP_BACKWARD <to FOR_ITER>
        END_FOR; POP_ITER; LOAD_CONST None; RETURN_VALUE

    For a list/set/dict comprehension, instead of YIELD_VALUE the elt is appended
    to a container that was initialised at the top.
    """
    is_gen = bool(code.co_flags & 0x20)
    instructions = list(dis.get_instructions(code))

    # Detect comprehension kind by scanning first few non-housekeeping instructions
    kind = "gen" if is_gen else None
    if not is_gen:
        # listcomp starts with BUILD_LIST 0; setcomp with BUILD_SET 0; dictcomp with BUILD_MAP 0
        for ins in instructions:
            if ins.opname in ("RESUME", "RETURN_GENERATOR", "POP_TOP", "CACHE", "NOP"):
                continue
            if ins.opname == "BUILD_LIST" and ins.arg == 0:
                kind = "list"
                break
            if ins.opname == "BUILD_SET" and ins.arg == 0:
                kind = "set"
                break
            if ins.opname == "BUILD_MAP" and ins.arg == 0:
                kind = "dict"
                break
            break  # something else → fall back

    if kind is None:
        # Not a clean comprehension; emit a Call placeholder
        return ast.Call(
            func=ast.Name(id="__comp__", ctx=ast.Load()),
            args=[outer_iter],
            keywords=[],
        )

    # Find the FOR_ITER that drives the outermost loop (the one fed by .0)
    for_iter_idx = None
    for j, ins in enumerate(instructions):
        if ins.opname == "FOR_ITER":
            # Check preceding LOAD_FAST .0
            for k in range(j - 1, -1, -1):
                if instructions[k].opname not in ("CACHE", "NOP", "RESUME"):
                    if instructions[k].opname in ("LOAD_FAST", "LOAD_FAST_BORROW") \
                            and instructions[k].argval == ".0":
                        for_iter_idx = j
                    break
            if for_iter_idx is not None:
                break

    if for_iter_idx is None:
        return ast.Call(
            func=ast.Name(id="__comp__", ctx=ast.Load()),
            args=[outer_iter],
            keywords=[],
        )

    # Identify the loop variable storage and the body
    loop_end_offset = instructions[for_iter_idx].argval
    idx_for_offset = {ins.offset: i for i, ins in enumerate(instructions)}
    loop_end_idx = idx_for_offset[loop_end_offset]

    # Skip NOT_TAKEN immediately after FOR_ITER
    body_start = for_iter_idx + 1
    while body_start < len(instructions) and instructions[body_start].opname in (
            "NOT_TAKEN", "NOP", "CACHE"):
        body_start += 1

    # Loop variable: STORE_FAST or UNPACK_SEQUENCE + STORE_FAST_STORE_FAST
    target_node = None
    body_first = body_start
    loop_var_push = None
    bs_ins = instructions[body_first]
    if bs_ins.opname in ("STORE_FAST", "STORE_NAME", "STORE_DEREF"):
        target_node = _store_name(bs_ins.argval)
        body_first += 1
    elif bs_ins.opname == "STORE_FAST_LOAD_FAST":
        if isinstance(bs_ins.argval, tuple):
            a, b = bs_ins.argval
        else:
            parts = bs_ins.argrepr.split(",")
            a = parts[0].strip()
            b = parts[1].strip()
        target_node = _store_name(a)
        body_first += 1
        # After this instruction the value of `b` is on the stack; remember so we
        # can push it into the body decompiler.
        loop_var_push = _name(b)
    elif bs_ins.opname == "UNPACK_SEQUENCE":
        n = bs_ins.arg
        body_first += 1
        targets = []
        for _ in range(n):
            ins = instructions[body_first]
            if ins.opname == "STORE_FAST":
                targets.append(_store_name(ins.argval))
                body_first += 1
            elif ins.opname == "STORE_FAST_STORE_FAST":
                if isinstance(ins.argval, tuple):
                    a, b = ins.argval
                else:
                    a, b = ins.argrepr.split(",")
                    a = a.strip(); b = b.strip()
                targets.append(_store_name(a))
                targets.append(_store_name(b))
                body_first += 1
                # STORE_FAST_STORE_FAST does two stores per instruction
                # adjust loop counter
                # the loop counter `_` is local, so we should subtract one from n manually
                # Simpler: leave the heuristic and let the loop naturally consume the right # of insts
                # Actually we want to track how many items have been stored. We had n popped
                # items in stack; each STORE_FAST consumes 1, each STORE_FAST_STORE_FAST consumes 2.
                # So we update _ counter accordingly. For now we accept the discrepancy if both targets
                # are stored — break out if we've got enough.
            else:
                break
        target_node = ast.Tuple(elts=targets, ctx=ast.Store())
    else:
        # Unknown loop var setup
        target_node = _store_name("_unknown_")
        body_first += 1

    # The elt expression: we run a sub-decompiler starting at body_first with an empty
    # stack and stop when we hit YIELD_VALUE / LIST_APPEND / SET_ADD / MAP_ADD.
    elt_node, end_idx, value_pair, if_filter = _decompile_comp_body(
        code, instructions, body_first, loop_end_idx, kind, loop_var=loop_var_push)

    # Build the appropriate comprehension AST
    ifs = [if_filter] if if_filter is not None else []
    comp = ast.comprehension(
        target=target_node, iter=outer_iter, ifs=ifs, is_async=0)
    if kind == "list":
        result = ast.ListComp(elt=elt_node, generators=[comp])
    elif kind == "set":
        result = ast.SetComp(elt=elt_node, generators=[comp])
    elif kind == "dict":
        k_node, v_node = value_pair
        result = ast.DictComp(key=k_node, value=v_node, generators=[comp])
    else:
        # genexp
        result = ast.GeneratorExp(elt=elt_node, generators=[comp])

    # Apply freevar rename: replace garbled freevars with their outer-scope names
    if freevar_map:
        result = _apply_name_map(result, freevar_map)
        ast.fix_missing_locations(result)

    return result


def _decompile_comp_body(code, instructions, start_idx, end_idx, kind, loop_var=None):
    """Decompile the inner body of a comprehension. Returns (elt_node, end_idx,
    value_pair_or_None, if_filter_or_None).

    If loop_var is provided, push it onto the stack at the start (handles
    STORE_FAST_LOAD_FAST patterns where the load part is implicitly part of
    the loop var capture).
    """
    dec = Decompiler(code, is_module=False)
    dec.stack = []
    dec.body = []
    if loop_var is not None:
        dec.stack.append(loop_var)

    i = start_idx
    elt = None
    value_pair = None
    if_filter = None
    while i < end_idx:
        ins = instructions[i]
        op = ins.opname
        if op == "YIELD_VALUE" and kind == "gen":
            if dec.stack:
                elt = dec.stack.pop()
            break
        if op == "LIST_APPEND" and kind == "list":
            if dec.stack:
                elt = dec.stack.pop()
            break
        if op == "SET_ADD" and kind == "set":
            if dec.stack:
                elt = dec.stack.pop()
            break
        if op == "MAP_ADD" and kind == "dict":
            if len(dec.stack) >= 2:
                v = dec.stack.pop()
                k = dec.stack.pop()
                value_pair = (k, v)
            break
        if op in ("POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE",
                  "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE"):
            cond = dec.stack.pop() if dec.stack else _name("__cond__")
            # filter pattern: POP_JUMP_IF X target ; JUMP_BACKWARD (skip)
            k2 = i + 1
            while k2 < end_idx and instructions[k2].opname == "NOT_TAKEN":
                k2 += 1
            if (k2 < end_idx
                    and instructions[k2].opname.startswith("JUMP_BACKWARD")):
                if op == "POP_JUMP_IF_TRUE":
                    if_filter = cond
                elif op == "POP_JUMP_IF_FALSE":
                    if_filter = ast.UnaryOp(op=ast.Not(), operand=cond)
                elif op == "POP_JUMP_IF_NONE":
                    if_filter = ast.Compare(left=cond, ops=[ast.IsNot()],
                                            comparators=[_const(None)])
                elif op == "POP_JUMP_IF_NOT_NONE":
                    if_filter = ast.Compare(left=cond, ops=[ast.Is()],
                                            comparators=[_const(None)])
                # Jump to the body target
                target_offset = ins.argval
                # Locate index of target offset
                target_idx_local = None
                for k_idx, k_ins in enumerate(instructions):
                    if k_ins.offset == target_offset:
                        target_idx_local = k_idx
                        break
                if target_idx_local is not None:
                    i = target_idx_local
                    continue
            i += 1
            continue
        if op in ("RESUME", "CACHE", "NOP", "NOT_TAKEN"):
            i += 1
            continue
        try:
            i = dec._exec_inst(i)
        except (IndexError, NotImplementedError, AssertionError, AttributeError, TypeError):
            i += 1
    return elt, i, value_pair, if_filter

class _UnpackMarker:
    def __init__(self, v, n):
        self.v = v
        self.n = n

class _UnpackElt:
    def __init__(self, v, idx):
        self.v = v
        self.idx = idx

class _UnpackEx:
    def __init__(self, v, before, after):
        self.v = v
        self.before = before
        self.after = after

class _WithMarker:
    def __init__(self, mgr):
        self.mgr = mgr

class _WithEnter:
    def __init__(self, mgr):
        self.mgr = mgr

class _WithExitMarker:
    def __init__(self, mgr):
        self.mgr = mgr

class _WithEnterMarker:
    def __init__(self, mgr):
        self.mgr = mgr


class _ImportRef:
    """A module reference produced by IMPORT_NAME."""
    def __init__(self, module, level, fromlist):
        self.module = module
        self.level = level
        self.fromlist = fromlist  # None or list of names


class _ImportFromAttr:
    """An attribute access on an _ImportRef (produced by IMPORT_FROM)."""
    def __init__(self, mod_ref, name):
        self.mod_ref = mod_ref
        self.name = name


def _store_name(name):
    n = _name(name)
    n.ctx = ast.Store()
    return n


def _strip_null(s):
    if not isinstance(s, str):
        return s
    # "name + NULL|self" / "name + NULL" → "name"
    if "+" in s:
        s = s.split("+")[0].strip()
    return s


def _is_same_expr(a, b):
    """Naive structural equality for ast nodes, used to detect when the LOAD_ATTR
    bound-method receiver matches the next positional arg."""
    if a is b:
        return True
    if type(a) is not type(b):
        return False
    if isinstance(a, ast.Name):
        return a.id == b.id
    if isinstance(a, ast.Attribute):
        return a.attr == b.attr and _is_same_expr(a.value, b.value)
    if isinstance(a, ast.Constant):
        return a.value == b.value
    if isinstance(a, ast.Subscript):
        return _is_same_expr(a.value, b.value) and _is_same_expr(a.slice, b.slice)
    return False


def _split_args_keywords(args_with_self):
    """Used by CALL: produce (args, keywords) lists from raw arg stack.

    With the 3.13+ KW_NAMES / call layout we may have keyword args at the tail.
    For our simple bytecode patterns we never set self._kw_names, so all args
    are positional.
    """
    return list(args_with_self), []


def _expr_of(fref):
    return _name("__fref__")


def _fref_to_lambda(fref, freevar_map=None):
    """Convert a _FunctionRef into an ast.Lambda expression (best-effort)."""
    code = fref.code
    n_pos = code.co_argcount
    n_kw = code.co_kwonlyargcount
    flags = code.co_flags
    has_vararg = bool(flags & 0x04)
    has_kwarg = bool(flags & 0x08)
    varnames = list(code.co_varnames)

    args = [ast.arg(arg=v) for v in varnames[:n_pos]]
    kwonly_args = [ast.arg(arg=v) for v in varnames[n_pos:n_pos+n_kw]]
    idx = n_pos + n_kw
    vararg = None
    if has_vararg:
        vararg = ast.arg(arg=varnames[idx])
        idx += 1
    kwarg = None
    if has_kwarg:
        kwarg = ast.arg(arg=varnames[idx])
        idx += 1
    defaults = []
    if fref.defaults is not None:
        if isinstance(fref.defaults, ast.Tuple):
            defaults = list(fref.defaults.elts)
        elif isinstance(fref.defaults, ast.Constant) and isinstance(fref.defaults.value, tuple):
            defaults = [ast.Constant(value=v) for v in fref.defaults.value]
        else:
            defaults = [fref.defaults]
    kw_defaults = [None] * len(kwonly_args)

    # Use per-lambda freevar map if available
    if freevar_map is None:
        freevar_map = {}

    body_stmts = _decompile_body(code, is_module=False)
    # A lambda must have a single expression body; if we have statements, return the last return value
    if len(body_stmts) == 1 and isinstance(body_stmts[0], ast.Return):
        body_expr = body_stmts[0].value
    else:
        # Best-effort: encode as a tuple of side effects then the final return
        body_expr = ast.Constant(value=None)
        for s in reversed(body_stmts):
            if isinstance(s, ast.Return):
                body_expr = s.value
                break

    lam = ast.Lambda(
        args=ast.arguments(
            posonlyargs=[], args=args, vararg=vararg,
            kwonlyargs=kwonly_args, kw_defaults=kw_defaults,
            kwarg=kwarg, defaults=defaults,
        ),
        body=body_expr,
    )
    if freevar_map:
        lam = _apply_name_map(lam, freevar_map)
        ast.fix_missing_locations(lam)
    return lam


def _class_def_from_ref(cref: "_ClassRef", name: str) -> ast.ClassDef:
    """Build an ast.ClassDef from a _ClassRef placeholder."""
    if cref.body_code is None:
        body = [ast.Pass()]
    else:
        body = _decompile_class_body(cref.body_code)
    if not body:
        body = [ast.Pass()]
    return ast.ClassDef(
        name=name,
        bases=list(cref.bases),
        keywords=[],
        body=body,
        decorator_list=[],
        type_params=[],
    )


def _decompile_class_body(code):
    """Decompile a class-body code object. Strip auto-generated header/footer.

    Also extracts the class's __annotate__ function (if present) to recover field
    annotations, which we then use to convert plain Assigns into AnnAssigns.
    """
    dec = Decompiler(code, is_module=False)
    dec.run()
    body = dec.body

    # Find annotations from __annotate_func__ bytecode
    annotations = _extract_annotations_from_code(code)

    out = []
    for s in body:
        if isinstance(s, ast.Assign) and len(s.targets) == 1 \
                and isinstance(s.targets[0], ast.Name) \
                and s.targets[0].id in ("__module__", "__qualname__", "__firstlineno__",
                                          "__static_attributes__",
                                          "__classdictcell__", "__annotate_func__"):
            continue
        if isinstance(s, ast.Assign) and len(s.targets) == 1 \
                and isinstance(s.targets[0], ast.Name) \
                and isinstance(s.value, ast.Call) \
                and isinstance(s.value.func, ast.Name) \
                and s.value.func.id == "locals" \
                and not s.value.args and not s.value.keywords:
            continue
        if isinstance(s, ast.FunctionDef) and s.name == "__annotate_func__":
            continue
        # Convert Assign(name=value) -> AnnAssign(name: ann, value) if annotation exists
        if (isinstance(s, ast.Assign)
                and len(s.targets) == 1
                and isinstance(s.targets[0], ast.Name)
                and s.targets[0].id in annotations):
            target = s.targets[0]
            ann_type = annotations[s.targets[0].id]
            out.append(ast.AnnAssign(
                target=ast.Name(id=target.id, ctx=ast.Store()),
                annotation=ast.Name(id=ann_type, ctx=ast.Load()),
                value=s.value,
                simple=1,
            ))
            # Mark as handled so we don't add a duplicate
            annotations.pop(s.targets[0].id)
            continue
        out.append(s)

    if out and isinstance(out[-1], ast.Return) \
            and isinstance(out[-1].value, ast.Constant) \
            and out[-1].value.value is None:
        out.pop()

    # Insert AnnAssigns for the remaining annotations (fields without default values).
    # These go FIRST in the class body for clarity.
    prefix = []
    for field_name, ann_type in annotations.items():
        prefix.append(ast.AnnAssign(
            target=ast.Name(id=field_name, ctx=ast.Store()),
            annotation=ast.Name(id=ann_type, ctx=ast.Load()),
            value=None,
            simple=1,
        ))
    return prefix + out


def _extract_annotations_from_code(class_body_code):
    """Scan the class body for the __annotate__ lambda and extract {name: type_name}.

    Strategy: find the __annotate_func__ child code object, walk its instructions
    looking for the pattern `LOAD_FROM_DICT_OR_GLOBALS <type>; ...; LOAD_CONST <name>;
    STORE_SUBSCR` (or variants).
    """
    ann_code = None
    for c in class_body_code.co_consts:
        if isinstance(c, types.CodeType) and c.co_name == "<lambda>" \
                and c.co_firstlineno == class_body_code.co_firstlineno:
            # this MIGHT be the annotate fn (it's the last lambda)
            ann_code = c
    if ann_code is None:
        return {}

    annotations = {}
    instrs = list(dis.get_instructions(ann_code))
    # Look for: LOAD_FROM_DICT_OR_GLOBALS <type> ... LOAD_CONST <name> ... STORE_SUBSCR
    for i, ins in enumerate(instrs):
        if ins.opname == "STORE_SUBSCR":
            # Walk back to find LOAD_CONST <name> (the dict key)
            name = None
            for k in range(i - 1, max(0, i - 6), -1):
                if instrs[k].opname == "LOAD_CONST" \
                        and isinstance(instrs[k].argval, str):
                    name = instrs[k].argval
                    break
            if name is None:
                continue
            # Find the value's type: LOAD_FROM_DICT_OR_GLOBALS just before that
            ann_type = "Any"
            for k in range(i - 1, max(0, i - 10), -1):
                if instrs[k].opname == "LOAD_FROM_DICT_OR_GLOBALS":
                    ann_type = instrs[k].argval
                    break
            annotations[name] = ann_type
    return annotations


def _unwrap_decorated_class(node: ast.Call):
    """If `node` is a chain of decorator Calls wrapping a ClassDef-like AST node,
    unwrap and return (ClassDef, decorators). Otherwise return None.

    Decorator chain: @dec1; @dec2; class Foo: ... compiles to
        dec1(dec2(__build_class__(<body_fn>, 'Foo')))
    where __build_class__ produces a class object that we represent as a _ClassRef.
    But by the time STORE_NAME runs, the _ClassRef has been wrapped in Call nodes.
    """
    decorators = []
    cur = node
    while isinstance(cur, ast.Call) and len(cur.args) == 1:
        decorators.append(cur.func)
        cur = cur.args[0]
    if isinstance(cur, _ClassRef):
        cls = _class_def_from_ref(cur, cur.name)
        return cls, decorators
    return None


def _function_def_from_ref(fref: "_FunctionRef", name: str) -> ast.FunctionDef:
    code = fref.code
    n_pos = code.co_argcount
    n_kw = code.co_kwonlyargcount
    n_posonly = code.co_posonlyargcount
    flags = code.co_flags
    has_vararg = bool(flags & 0x04)
    has_kwarg = bool(flags & 0x08)
    varnames = list(code.co_varnames)

    posonly = [ast.arg(arg=v) for v in varnames[:n_posonly]]
    args = [ast.arg(arg=v) for v in varnames[n_posonly:n_pos]]
    kwonly_args = [ast.arg(arg=v) for v in varnames[n_pos:n_pos+n_kw]]
    idx = n_pos + n_kw
    vararg = None
    if has_vararg:
        vararg = ast.arg(arg=varnames[idx])
        idx += 1
    kwarg = None
    if has_kwarg:
        kwarg = ast.arg(arg=varnames[idx])
        idx += 1

    # defaults / kw_defaults expressions, if any
    defaults = []
    if fref.defaults is not None:
        if isinstance(fref.defaults, ast.Tuple):
            defaults = list(fref.defaults.elts)
        elif isinstance(fref.defaults, ast.List):
            defaults = list(fref.defaults.elts)
        elif (isinstance(fref.defaults, ast.Constant)
                and isinstance(fref.defaults.value, tuple)):
            defaults = [ast.Constant(value=v) for v in fref.defaults.value]
        else:
            defaults = [fref.defaults]

    kw_defaults_list = [None] * len(kwonly_args)
    if fref.kw_defaults is not None and isinstance(fref.kw_defaults, ast.Dict):
        # ast.Dict of {keyword_name: default_value}
        kw_map = {}
        for k, v in zip(fref.kw_defaults.keys, fref.kw_defaults.values):
            if isinstance(k, ast.Constant):
                kw_map[k.value] = v
        kw_defaults_list = [kw_map.get(a.arg, None) for a in kwonly_args]

    is_async = bool(code.co_flags & 0x100)

    body = _decompile_body(code, is_module=False)
    if not body:
        body = [ast.Pass()]

    cls = ast.AsyncFunctionDef if is_async else ast.FunctionDef
    return cls(
        name=name,
        args=ast.arguments(
            posonlyargs=posonly,
            args=args,
            vararg=vararg,
            kwonlyargs=kwonly_args,
            kw_defaults=kw_defaults_list,
            kwarg=kwarg,
            defaults=defaults,
        ),
        body=body,
        decorator_list=[],
        returns=None,
        type_params=[],
    )


class _SubDecompiler:
    """A view into the parent Decompiler that shares its stack but maintains
    its own body list. Used for nested if/for body decoding."""
    def __init__(self, parent):
        self.parent = parent
        self.code = parent.code
        self.instructions = parent.instructions
        self.idx_for_offset = parent.idx_for_offset
        self.stack = parent.stack  # shared!
        self.body = []
        self.is_module = parent.is_module
        self.is_generator = parent.is_generator
        self.jump_targets = parent.jump_targets
        self._next_idx = 0


def _decompile_segment(sub, parent, start_idx, end_idx,
                       backjump_offset=None,
                       stop_on_forward_past=None):
    """Decompile parent.instructions[start_idx:end_idx] into sub.body.

    Returns (stmts, next_index). next_index is positioned at the first
    instruction NOT included in the segment (the terminator).
    """
    i = start_idx
    save_body = parent.body
    parent.body = sub.body
    try:
        while i < end_idx:
            ins = parent.instructions[i]
            op = ins.opname
            # Stop conditions
            if op.startswith("JUMP_BACKWARD"):
                # If the segment is tracking a backjump, only break on a match.
                # Otherwise (we're in a nested branch), any backjump means we've
                # reached a loop boundary and should hand back to the enclosing
                # decompiler.
                if backjump_offset is None or ins.argval == backjump_offset:
                    break
                # A non-matching JUMP_BACKWARD inside the segment is unusual but
                # safe to ignore (treat as a continue-style jump).
                i += 1
                continue
            if stop_on_forward_past is not None and op == "JUMP_FORWARD":
                # this jump moves past the if-true block: the segment ends here
                break

            if op == "FOR_ITER":
                i = parent._for_loop(i, end_idx)
                continue
            if op in ("POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE",
                      "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE"):
                i = parent._if_else(i, end_idx)
                continue
            # with statement: COPY 1 ; LOAD_SPECIAL 1 (__exit__) ; ...
            if op == "COPY" and ins.arg == 1 and i + 6 < end_idx \
                    and parent.instructions[i+1].opname == "LOAD_SPECIAL" \
                    and parent.instructions[i+1].arg == 1:
                i = parent._with_stmt(i, end_idx)
                continue
            if op == "RETURN_VALUE":
                value = parent.stack.pop()
                parent.body.append(ast.Return(value=value))
                i += 1
                continue
            if op == "RETURN_CONST":
                parent.body.append(ast.Return(value=_const(ins.argval)))
                i += 1
                continue
            if op in ("END_FOR", "POP_ITER", "POP_BLOCK"):
                break
            try:
                i = parent._exec_inst(i)
            except (IndexError, AssertionError, NotImplementedError, AttributeError, TypeError) as e:
                parent.body.append(ast.Expr(value=ast.Call(
                    func=ast.Name(id="__decode_failed__", ctx=ast.Load()),
                    args=[ast.Constant(value=f"{op}@{ins.offset}:{type(e).__name__}")],
                    keywords=[]
                )))
                i += 1
    finally:
        parent.body = save_body
    sub._next_idx = i
    return sub.body, i


def _consume_for_target(sub, parent, j):
    """Consume the loop-variable store from instructions starting at j.
    Returns the AST target and advances sub._next_idx.
    """
    ins = parent.instructions[j]
    if ins.opname in ("STORE_FAST", "STORE_NAME", "STORE_DEREF", "STORE_GLOBAL"):
        target = _store_name(ins.argval)
        sub._next_idx = j + 1
        return target
    if ins.opname == "STORE_FAST_LOAD_FAST":
        # Specialised: store TOS to varA AND immediately load varA (so it stays on stack
        # for the next instruction). Same name for both in the obfuscated bytecode pattern.
        if isinstance(ins.argval, tuple):
            a, b = ins.argval
        else:
            a, b = ins.argrepr.split(",")
            a = a.strip(); b = b.strip()
        sub._next_idx = j + 1
        # Push the load result onto the parent's stack so subsequent instructions can use it
        parent.stack.append(_name(b))
        return _store_name(a)
    if ins.opname == "STORE_FAST_STORE_FAST":
        # Two-store specialized: stores two consecutive locals from a tuple unpack.
        # The arg encodes both names. Sets element 0 to first, element 1 to second.
        if isinstance(ins.argval, tuple):
            a, b = ins.argval
        else:
            a, b = ins.argrepr.split(",")
            a = a.strip(); b = b.strip()
        sub._next_idx = j + 1
        return ast.Tuple(elts=[_store_name(a), _store_name(b)], ctx=ast.Store())
    if ins.opname == "UNPACK_SEQUENCE":
        n = ins.arg
        targets = []
        k = j + 1
        consumed = 0
        while consumed < n:
            ins2 = parent.instructions[k]
            if ins2.opname in ("STORE_FAST", "STORE_NAME"):
                targets.append(_store_name(ins2.argval))
                consumed += 1
                k += 1
            elif ins2.opname == "STORE_FAST_STORE_FAST":
                if isinstance(ins2.argval, tuple):
                    a, b = ins2.argval
                else:
                    a, b = ins2.argrepr.split(",")
                    a = a.strip(); b = b.strip()
                targets.append(_store_name(a))
                targets.append(_store_name(b))
                consumed += 2
                k += 1
            else:
                raise NotImplementedError(f"Unexpected loop unpack store: {ins2.opname}")
        sub._next_idx = k
        return ast.Tuple(elts=targets, ctx=ast.Store())
    # Fallback: implicit loop var (used by all()/any() inline-loop patterns).
    # We don't actually advance — the body decoder will treat TOS as the iter value.
    sub._next_idx = j
    parent.stack.append(_name("_loop_val"))
    return _store_name("_loop_val")


# ---------------------------------------------------------------------------
# Top-level wiring
# ---------------------------------------------------------------------------

def _is_transparent_except_handler_insts(insts, offset_map, target_offset: int) -> bool:
    """Return True if the exception handler at target_offset is a bare re-raise.

    Handles two patterns:
    1. PUSH_EXC_INFO-based (depth=0): `except ANYTHING: raise`
    2. SWAP-based (depth>0): comprehension cleanup — SWAP; POP_TOP; SWAP; STORE_FAST*; RERAISE
    """
    if target_offset not in offset_map:
        return False
    i = offset_map[target_offset]

    # Pattern 1: PUSH_EXC_INFO-based transparent re-raise
    if insts[i].opname == "PUSH_EXC_INFO":
        i += 1
        skip_ops = {"CACHE", "NOP", "NOT_TAKEN", "LOAD_GLOBAL", "LOAD_NAME",
                    "LOAD_ATTR", "LOAD_COMMON_CONSTANT",
                    "CHECK_EXC_MATCH", "POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE"}
        while i < len(insts) and insts[i].opname in skip_ops:
            i += 1
        if i >= len(insts):
            return False
        if insts[i].opname != "POP_TOP":
            return False
        i += 1
        while i < len(insts) and insts[i].opname in ("NOT_TAKEN", "CACHE", "NOP"):
            i += 1
        if i >= len(insts):
            return False
        op = insts[i].opname
        return op == "RAISE_VARARGS" or op == "RERAISE"

    # Pattern 2: SWAP-based transparent re-raise (comprehension cleanup at depth>0)
    # Pattern: SWAP; POP_TOP; SWAP; STORE_FAST*; RERAISE
    if insts[i].opname == "SWAP":
        j = i
        # Skip SWAP, POP_TOP, SWAP, STORE_FAST sequences
        while j < len(insts) and insts[j].opname in ("SWAP", "POP_TOP", "STORE_FAST", "STORE_NAME",
                                                       "NOP", "NOT_TAKEN", "CACHE"):
            j += 1
        if j < len(insts) and insts[j].opname == "RERAISE":
            return True
        return False

    return False


def _is_transparent_except_handler(code: types.CodeType, target_offset: int) -> bool:
    """Return True if the exception handler at target_offset is a bare re-raise."""
    insts = list(dis.get_instructions(code))
    offset_map = {ins.offset: k for k, ins in enumerate(insts)}
    return _is_transparent_except_handler_insts(insts, offset_map, target_offset)


def _classify_exception_table(code: types.CodeType):
    """Classify exception table entries into transparent (re-raise only) vs real.

    Returns (transparent_targets, real_entries) where:
    - transparent_targets: set of target offsets that are bare re-raises
    - real_entries: list of non-lasti entries with non-transparent handlers, sorted by start
    """
    try:
        entries = list(dis._parse_exception_table(code))
    except Exception:
        return set(), []
    if not entries:
        return set(), []

    insts = list(dis.get_instructions(code))
    offset_map = {ins.offset: k for k, ins in enumerate(insts)}

    transparent_targets = set()
    real_entries = []
    for entry in entries:
        if entry.lasti:
            continue
        if _is_transparent_except_handler_insts(insts, offset_map, entry.target):
            transparent_targets.add(entry.target)
        else:
            real_entries.append(entry)

    real_entries.sort(key=lambda e: e.start)
    return transparent_targets, real_entries


def _parse_real_handler(code: types.CodeType, target_offset: int):
    """Parse a real exception handler (non-transparent) and return (exc_type_name, body_stmts, after_offset).

    For `except ValueError: pass`:
        PUSH_EXC_INFO
        LOAD_GLOBAL ValueError
        CHECK_EXC_MATCH
        POP_JUMP_IF_FALSE <reraise>
        NOT_TAKEN
        POP_TOP
        POP_EXCEPT
        JUMP_FORWARD <after>
        RERAISE 0       <- re-raise for non-matching
        COPY 3          <- lasti handler
        POP_EXCEPT
        RERAISE 1

    Returns (exc_type_name, handler_body, after_offset) or (None, None, None) if not parseable.
    after_offset is where normal code resumes (the JUMP_FORWARD target).
    """
    insts = list(dis.get_instructions(code))
    offset_map = {ins.offset: k for k, ins in enumerate(insts)}
    if target_offset not in offset_map:
        return None, None, None
    i = offset_map[target_offset]

    if i >= len(insts) or insts[i].opname != "PUSH_EXC_INFO":
        return None, None, None
    i += 1

    # Find exception type name (LOAD_GLOBAL ExcType; CHECK_EXC_MATCH; POP_JUMP_IF_FALSE <reraise>)
    exc_type_name = None
    while i < len(insts) and insts[i].opname in ("CACHE", "NOP", "NOT_TAKEN"):
        i += 1
    if i < len(insts) and insts[i].opname in ("LOAD_GLOBAL", "LOAD_NAME"):
        exc_type_name = insts[i].argval
        if exc_type_name and " " in exc_type_name:
            exc_type_name = exc_type_name.split()[0]
        i += 1
    while i < len(insts) and insts[i].opname in ("CACHE", "NOP", "NOT_TAKEN"):
        i += 1
    if i < len(insts) and insts[i].opname == "CHECK_EXC_MATCH":
        i += 1
    while i < len(insts) and insts[i].opname in ("CACHE", "NOP", "NOT_TAKEN"):
        i += 1
    # POP_JUMP_IF_FALSE to the reraise block
    if i < len(insts) and insts[i].opname == "POP_JUMP_IF_FALSE":
        i += 1
    while i < len(insts) and insts[i].opname in ("CACHE", "NOP", "NOT_TAKEN"):
        i += 1

    # Now we should see POP_TOP (discard exception value for `pass` body)
    # then POP_EXCEPT then JUMP_FORWARD <after>
    if i < len(insts) and insts[i].opname == "POP_TOP":
        i += 1
    while i < len(insts) and insts[i].opname in ("CACHE", "NOP", "NOT_TAKEN"):
        i += 1

    # Handler body: between POP_TOP and POP_EXCEPT/JUMP_FORWARD
    # For simple `except Exc: pass`, the body is empty (just POP_EXCEPT + JUMP_FORWARD)
    handler_stmts = []
    after_offset = None
    while i < len(insts):
        op = insts[i].opname
        if op == "POP_EXCEPT":
            i += 1
            while i < len(insts) and insts[i].opname in ("CACHE", "NOP", "NOT_TAKEN"):
                i += 1
            if i < len(insts) and insts[i].opname == "JUMP_FORWARD":
                after_offset = insts[i].argval
            break
        if op in ("CACHE", "NOP", "NOT_TAKEN"):
            i += 1
            continue
        if op == "JUMP_FORWARD":
            after_offset = insts[i].argval
            break
        # Any other instruction is part of the handler body — emit pass for now
        break

    if not handler_stmts:
        handler_stmts = [ast.Pass()]

    if exc_type_name:
        # Strip obfuscated prefix if present (e.g. "ValueError" is already clean)
        pass
    return exc_type_name, handler_stmts, after_offset


def _has_only_transparent_handlers(code: types.CodeType) -> bool:
    """Return True if every non-lasti exception table entry's handler is a bare re-raise."""
    _, real_entries = _classify_exception_table(code)
    try:
        entries = list(dis._parse_exception_table(code))
    except Exception:
        return False
    primary = [e for e in entries if not e.lasti]
    return bool(primary) and not real_entries


def _trim_to_handler_start(code: types.CodeType) -> int:
    """Return the minimum handler offset among all non-lasti exception table entries.

    The decompiler should stop before this offset so the handler code is never walked.
    Returns 10**9 if no entries, meaning no trimming.
    """
    try:
        entries = list(dis._parse_exception_table(code))
    except Exception:
        return 10**9
    primary = [e for e in entries if not e.lasti]
    if not primary:
        return 10**9
    return min(e.target for e in primary)


def _decompile_body(code: types.CodeType, is_module: bool):
    """Decompile a code object's body to a list of AST statements.

    Round-11 strategy:
    1. Classify exception table entries as transparent (bare re-raise) or real.
    2. If all non-lasti handlers are transparent, cap the walk at the first handler
       offset — strips the outer `try: body except BaseException: raise` wrapper.
    3. If there are real inner handlers (e.g. `except ValueError: pass`), decompile
       the code in segments, wrapping real try-body ranges in ast.Try nodes.
    """
    transparent_targets, real_entries = _classify_exception_table(code)

    # Build a set of all handler-start offsets so the post-RETURN check can stop there.
    try:
        all_entries = list(dis._parse_exception_table(code))
    except Exception:
        all_entries = []
    all_handler_offsets = {e.target for e in all_entries}

    dec = Decompiler(code, is_module=is_module)
    dec.handler_offsets = all_handler_offsets  # used by _is_unreachable_trailer

    # Find the outermost transparent wrapper cap.
    outer_cap_offset = 10**9
    if all_entries:
        transparent_non_lasti = [e for e in all_entries
                                  if not e.lasti and e.target in transparent_targets]
        if transparent_non_lasti:
            outer_cap_offset = min(e.target for e in transparent_non_lasti)

    outer_cap_idx = len(dec.instructions)
    for k, ins in enumerate(dec.instructions):
        if ins.offset >= outer_cap_offset:
            outer_cap_idx = k
            break

    if not real_entries:
        # Simple case: only transparent handlers — cap and walk.
        dec._walk(0, outer_cap_idx)
    else:
        # Complex case: there are real inner try/except blocks.
        # Sort real entries by start offset and decompile in segments.
        _walk_with_try_except(dec, code, real_entries, outer_cap_idx, all_handler_offsets)

    body = dec.body
    # Drop trailing implicit `return None`
    if not is_module and body and isinstance(body[-1], ast.Return):
        last = body[-1]
        if isinstance(last.value, ast.Constant) and last.value.value is None:
            body.pop()
    if is_module:
        body = [s for s in body if not isinstance(s, ast.Return)]
    return body


def _walk_with_try_except(dec: "Decompiler", code: types.CodeType,
                           real_entries, outer_cap_idx: int,
                           all_handler_offsets):
    """Walk bytecode in segments, inserting ast.Try nodes for real exception handlers.

    We walk from offset 0 up to outer_cap_idx. Whenever we enter a try-body range
    (as defined by a real_entries entry), we:
      1. Decompile the try body using a child Decompiler.
      2. Parse the exception handler.
      3. Build an ast.Try node.
      4. Resume walking from after the handler.
    """
    insts = dec.instructions
    offset_map = dec.idx_for_offset

    # Build a map: try-body start index -> (try-body end index, handler target offset)
    # A try body may contain multiple instructions; we use the entry's start/end offsets.
    try_starts = {}  # start_idx -> (end_idx_exclusive, handler_target_offset)
    for entry in real_entries:
        s_idx = offset_map.get(entry.start)
        if s_idx is None:
            continue
        # Find end idx: first instruction with offset > entry.end
        e_idx = outer_cap_idx
        for k in range(s_idx, outer_cap_idx):
            if insts[k].offset > entry.end:
                e_idx = k
                break
        try_starts[s_idx] = (e_idx, entry.target)

    # Walk from 0 to outer_cap_idx, detecting try block boundaries.
    i = 0
    while i < outer_cap_idx:
        if i in try_starts:
            body_end_idx, handler_target = try_starts[i]

            # Decompile try body in a child decompiler sharing state
            child = Decompiler(code, is_module=dec.is_module)
            child.handler_offsets = all_handler_offsets
            child.stack = list(dec.stack)  # inherit current stack
            child._walk(i, body_end_idx)
            try_body = child.body

            # Strip trailing implicit None return from try body if present
            if try_body and isinstance(try_body[-1], ast.Return):
                last = try_body[-1]
                if isinstance(last.value, ast.Constant) and last.value.value is None:
                    try_body = try_body[:-1]
            if not try_body:
                try_body = [ast.Pass()]

            # Parse the handler
            exc_type_name, handler_body, after_offset = _parse_real_handler(code, handler_target)
            if exc_type_name is None:
                # Can't parse handler — fall back to emitting body as-is and skipping
                dec.body.extend(try_body)
                i = body_end_idx
                continue

            exc_type_node = ast.Name(id=exc_type_name, ctx=ast.Load())
            handler = ast.ExceptHandler(type=exc_type_node, name=None, body=handler_body)
            try_node = ast.Try(
                body=try_body,
                handlers=[handler],
                orelse=[],
                finalbody=[],
            )
            dec.body.append(try_node)

            # Resume at the instruction after the handler (JUMP_FORWARD target)
            if after_offset is not None and after_offset in offset_map:
                i = offset_map[after_offset]
            else:
                i = body_end_idx
        else:
            # Normal instruction — delegate to the single-instruction handler
            ins = insts[i]
            op = ins.opname

            # Check for structured constructs that the walker handles
            if op == "FOR_ITER":
                i = dec._for_loop(i, outer_cap_idx)
                continue
            if op in ("POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE",
                      "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE"):
                i = dec._if_else(i, outer_cap_idx)
                continue
            if op in ("JUMP_FORWARD", "JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT"):
                break
            if op == "COPY" and i + 6 < outer_cap_idx \
                    and insts[i+1].opname == "LOAD_SPECIAL" and insts[i+1].arg == 1:
                i = dec._with_stmt(i, outer_cap_idx)
                continue
            if op in ("RETURN_VALUE", "RETURN_CONST"):
                if op == "RETURN_VALUE":
                    value = dec.stack.pop() if dec.stack else ast.Constant(value=None)
                    dec.body.append(ast.Return(value=value))
                else:
                    dec.body.append(ast.Return(value=ast.Constant(value=ins.argval)))
                i += 1
                # Stop if the rest is just handler cleanup
                if not dec.stack and _is_handler_boundary(insts, i, all_handler_offsets):
                    break
                continue
            if op in ("END_FOR", "POP_ITER", "POP_BLOCK"):
                break
            try:
                i = dec._exec_inst(i)
            except (IndexError, AssertionError, NotImplementedError, AttributeError, TypeError) as e:
                dec.body.append(ast.Expr(value=ast.Call(
                    func=ast.Name(id="__decode_failed__", ctx=ast.Load()),
                    args=[ast.Constant(value=f"{op}@{ins.offset}:{type(e).__name__}")],
                    keywords=[]
                )))
                i += 1


def _is_handler_boundary(insts, i, handler_offsets):
    """Return True if instruction at index i is a known exception handler start.

    Used to stop walking after RETURN_VALUE when the next code is a handler.
    """
    if i >= len(insts):
        return True
    return insts[i].offset in handler_offsets


def decompile_module(code: types.CodeType) -> ast.Module:
    """Top-level: decompile a module's code object."""
    body = _decompile_body(code, is_module=True)
    mod = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(mod)
    return mod
