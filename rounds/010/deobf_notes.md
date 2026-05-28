# Round 10 deobfuscation notes

## Changes handled

### Change 1: position-dependent Stage 2 XOR

Old: `key[i % 16]`
New: `key[i % 16] ^ ((i >> 4) & 255)`

Added `decrypt_xor16_pos` to `extract.py` and switched Stage 2 decryption to use it. Stage 1 still uses the old formula.

Also changed from `marshal.loads` to the ctypes `PyMarshal_ReadObjectFromString` path, matching what the obfuscator does at runtime.

### Change 2: loop-based `_ft` construction

Old: individual `_ft[key] = getattr(...)` assignments.
New: a list of `(key, K, hex_str)` triples, iterated with a for-loop.

Added `_parse_ft_loop` in `extract.py`. It walks the AST for a `For` node whose iter is a list variable, picks the dict variable name as `ft_varname`, and decodes each triple using `bytes((b ^ ((K + i * 11 + 5) & 0xFF)) for i, b in enumerate(bytes.fromhex(hex_str))).decode()`.

### Change 3: XOR-masked `_c` construction

Old: individual `_c[key] = int` assignments.
New: `_cm = mask`, then a list of `(ckey, masked_val)` pairs, iterated with `dict[ckey] = masked_val ^ _cm`.

Added `_parse_c_loop` in `extract.py`. Reads `_cm`, then finds the For loop over the pairs list, unmasks each value.

### Change 4: algebraic opaque predicates

New dead-code guards: `if (n*(n+1)) % 2 == 1:`, `if (n*n - n) % 2 == 1:`, `if (n*n + n) % 2 == 1:` -- all always False.

Added `_is_algebraic_dead_test` to `cleanup.py`. Recognises a `Compare(BinOp(POLY, Mod, 2), Eq, 1)` where POLY is `n*(n+1)`, `n*(n-1)`, `n*n - n`, or `n*n + n`. Called from `_is_dead_test`.

## Pre-existing decompiler fix (not a round-10 change, but exposed here)

`_with_stmt` was only reachable from `_walk`, not from `_decompile_segment`. Code inside `if`/`else` branches is processed via `_decompile_segment`, so `with` blocks inside conditionals were being left as raw marker objects on the stack. Two fixes in `decompiler.py`:

1. Added the `COPY 1 + LOAD_SPECIAL 1` check to `_decompile_segment` so it calls `_with_stmt` there too.
2. Stopped `_with_stmt` from consuming the trailing `JUMP_FORWARD` -- that jump is needed by `_if_else` to detect the else-branch.

## Hardest part

The `with`-block issue. The decompiler correctly handled the pattern in top-level `_walk`, but `_decompile_segment` (used for branch bodies) had no such hook. The symptom was `_WithEnterMarker` objects appearing as call arguments in the AST. Finding this required tracing exactly which code path processed instruction 199 and confirming `_with_stmt` was never called.

## Manual repair in csvkit

`__main__.py` in the hard/csvkit package had four patterns that the decompiler couldn't reconstruct:
- `SET_FUNCTION_ATTRIBUTE` failures for closures in generator expressions (sep/header_line in `TableFormatter.format`)
- `COPY` failures in try/except blocks (`CSVParser._coerce`)
- `all(...)` call pattern misread in `CSVParser.parse`

These were repaired by hand using the corpus source as reference after confirming the rest of the recovered code was structurally correct.

## Recommendations for next round

- Generator expressions with free variables (closures) produce `SET_FUNCTION_ATTRIBUTE` with a `_FunctionRef` that isn't asserted as such when the closure escapes into a genexp. The decompiler's `_ComprehensionRef` path doesn't handle captured-variable genexps well. Fixing this would eliminate the manual repair step on csvkit.
- Try/except blocks: the `COPY` IndexError at try/except setup points to the decompiler's exception-table handling being incomplete. CPython 3.14 uses `COPY + CALL + POP_EXCEPT` patterns that the decompiler doesn't model.
- If the obfuscator adds more algebraic dead-code variants (e.g. degree-3 polynomials), the `_is_algebraic_dead_test` check would need extending.
