# Round 11 deobfuscation notes

## What changed in round 11

### Change 1: Stage 2 is a marshal'd code object

In rounds 8-10, Stage 1 decrypted to Python source text (Stage 2). Round 11 changes Stage 2 to be a compiled code object:

```python
_src = __import__('marshal').loads(zlib.decompress(decrypt_xor16(_D, _K)))
```

The `stage1_decode` function in `extract.py` now detects the `marshal.loads` pattern in the Stage 1 source and routes through `decompile_module` instead of `.decode("utf-8")`.

The `_ft` and `_c` list construction in Stage 2 also changed from direct subscript assignment to loop-based construction using `[*((tuples))]` spread syntax. `BUILD_LIST 0; LIST_EXTEND 1` in bytecode produces a `List(Starred(Tuple(...)))` node. `_expand_list_elts` in `extract.py` normalises this.

### Change 2: Transparent try/except wrappers

Every function body is wrapped in `try: <body> except BaseException: raise`. CPython 3.14 exception tables encode this as non-lasti entries all targeting the same `PUSH_EXC_INFO; LOAD_GLOBAL BaseException; CHECK_EXC_MATCH; POP_JUMP_IF_FALSE; POP_TOP; RAISE_VARARGS 0` handler.

The decompiler strips these by capping the instruction walk at the first transparent handler offset. The classification function `_classify_exception_table` distinguishes transparent handlers (including CPython's SWAP-based comprehension-cleanup re-raises at depth > 0) from real `except ValueError: pass` handlers.

For functions that contain real inner `try/except` blocks (like `_coerce`), the decompiler uses `_walk_with_try_except` to decompile in segments, generating proper `ast.Try` nodes.

### Change 3: New dead-code predicates

Round 11 adds two new categories of always-False dead-code tests:

- `isinstance(LITERAL, TYPE)` where the literal cannot be of that type: e.g. `isinstance(0, float)`, `isinstance(True, str)`. Handled by `_is_isinstance_dead_test` in `cleanup.py`.
- `sys.maxsize < 0`, `sys.version_info < (1, 0)`, `sys.version_info > (99, 0)`, `sys.float_info.max < 0`. Handled by `_is_sys_dead_test`. The comparator can be either `ast.Tuple` or `ast.Constant(tuple)` depending on CPython's constant folding.

## CPython 3.14 bytecode specifics

### `STORE_FAST_LOAD_FAST` combined opcode

Used in for loop bodies: stores the loop variable and immediately loads it. Treated as a combined `STORE_FAST; LOAD_FAST`.

### `LOAD_FAST_BORROW`

A borrow-semantics variant of `LOAD_FAST`. Treated identically.

### `LOAD_SMALL_INT`

Pushes small integer constants directly encoded in the instruction arg.

### `SET_FUNCTION_ATTRIBUTE`

Sets attributes on a function object (defaults, kw_defaults, closure). Now accepts `_ComprehensionRef` in addition to `_FunctionRef`.

### `LOAD_COMMON_CONSTANT`

Used for identity checks against built-in objects: `LOAD_GLOBAL all; COPY 1; LOAD_COMMON_CONSTANT all; IS_OP 0`. Always evaluates to True and is stripped by `Cpp314BuiltinIdentitySimplifier`.

## Additional decompiler fixes

### Stack snapshot before else-branch

`_if_else` now saves a snapshot of the parent stack before the true branch and restores it before the else branch. Without this, values produced by the true branch leak into the else branch's starting stack state, causing `CALL` to use the wrong callable.

### Skip-pattern guard for nested if-else

The skip pattern (`POP_JUMP_IF_X; JUMP_BACKWARD → if cond: body_at_target`) now guards against consuming the outer context's else-body when `target_idx >= end`. Instead it emits `continue` for the JUMP_BACKWARD.

### Ternary expression in inline comprehensions

`_try_inline_comp` now detects conditional element expressions inside list comprehensions:
`POP_JUMP_IF_NONE <else> ; <true_expr> ; JUMP_FORWARD ; <else_expr> ; LIST_APPEND`
→ `true_expr if x is not None else else_expr`.

Previously the JUMP_FORWARD was treated as a no-op, causing the else-branch value to be used as the element.

### SWAP-based transparent handlers

`_is_transparent_except_handler_insts` now also recognises CPython's SWAP-based comprehension cleanup handlers (depth > 0): `SWAP; POP_TOP; SWAP; STORE_FAST*; RERAISE`. Previously these were classified as non-transparent, causing `_has_only_transparent_handlers` to return False for functions containing inline comprehensions, which broke the outer transparent-wrapper cap logic.

## Cleanup passes added

### `TryExceptUnwrapper`

Strips AST-level `try: <body> except X: raise` wrappers as a second pass, catching cases the decompiler-level cap doesn't handle.

### `Cpp314BuiltinIdentitySimplifier`

Removes CPython 3.14 builtin-identity optimisation artifacts:
- `if all is all: <fast_inline_loop>` (always True, fast-path is discarded if it's just an inline loop replica of the slow-path `all()` call)
- `if True(genexpr):` (decompiler artifact for the slow path when the callable resolved incorrectly)
- Bare `all` / `len` / etc expression statements left over from `LOAD_GLOBAL` before the `IS_OP` check

## Remaining known limitations

- `column()` method in `CSVParser`: returns `[None for row in self._rows]` instead of the correct `[row[col_idx] for row in self._rows]`. The list comprehension element is `None` rather than the subscript — this is a decompiler edge case with the `STORE_FAST_LOAD_FAST` opcode inside inline comprehensions not capturing the element correctly.
- `sort_by()` lambda: captures a free variable with an obfuscated name (`lllIIlIlIIIllII`) rather than the local column-index variable (`lIllIIIIIlIllIl`). The lambda closure captures an obfuscated slot.
- `TableFormatter.format`: the border-line generator uses `lIllllllIIIIllI.padding` instead of `self.padding` — `lIllllllIIIIllI` is a mis-resolved reference to the padding value.
- All identifiers remain in their obfuscated form. No name-hint map was provided so `IdentifierRenamer` was not applied.
