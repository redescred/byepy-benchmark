# Round 12 deobfuscation notes

## Changes vs round 11

### Stage 1 XOR formula (extract.py)

Round 11 used `b ^ K[i%16]`. Round 12 changed it to `b ^ K[i%16] ^ ((i*7+13)&255)`. Added `decrypt_xor16_s1_r12()` and detect the round by checking for `_i*7+13` in the stage 1 source text.

### ClosureCaptureTransformer (cleanup.py, recover.py)

New obfuscation pass wraps each function's final `return EXPR` as:

```python
_clXXXX = EXPR
def _fYYYY():
    return <garbled_freevar>   # different name due to scrub_code
return _fYYYY()
```

Added `ClosureUnwrapper` in cleanup.py: detects the Assign/FunctionDef/Return-call triplet at any nesting depth and replaces it with `return EXPR` (using the outer Assign's RHS, discarding the garbled inner name). Applied twice in recover.py: before and after `TryExceptUnwrapper`.

### Freevar garbling in genexps and lambdas (decompiler.py, cleanup.py)

`scrub_code()` garbles `co_freevars` (child) and `co_cellvars` (parent) independently. Any lambda or genexp that captures a variable from the outer scope gets a garbled name that does not match the outer scope's name for the same variable. This caused `NameError` at runtime in the hard-tier csvkit `TableFormatter.format` method (genexps using `self.padding` and the padding string `p`).

Fix: added `FreevarResolver` class in cleanup.py. It traces the bytecode of each code object to find `SET_FUNCTION_ATTRIBUTE closure` sequences, reads the `BUILD_TUPLE` arguments preceding each such sequence (which are the cell values being captured), and maps `co_freevars[i]` in the child to the outer-scope name of the corresponding loaded value.

Modified `_build_comprehension` and `_fref_to_lambda` in decompiler.py to accept and apply a per-code-object freevar rename map. The module-level `_current_freevar_resolver` is set by recover.py before decompilation and cleared after.

One conflict existed: `lIllllllIIIIllI` mapped to both `self` (in one genexp) and `llIlIllllIllllI` (the padding string `p`, in another genexp of the same function). The scoped approach resolves this correctly since each genexp gets its own independent rename map.

## What still fails

Nothing - all three tiers pass behavioral and AST checks. AST scores range from 0.80 to 0.92 (all above the 0.6 threshold). The main source of AST score loss is residual obfuscated local variable names (the `lI...` identifiers in loop bodies and assignments), which are correct but renamed. Function names for trampoline functions remain as `func_NNNNN`.

## Files modified

- `rounds/012/work/extract.py` - added `decrypt_xor16_s1_r12`, updated `stage1_decode` detection
- `rounds/012/work/cleanup.py` - added `ClosureUnwrapper` and `FreevarResolver` classes
- `rounds/012/work/decompiler.py` - added `_apply_name_map`, `_current_freevar_resolver` global, modified `_build_comprehension` and `_fref_to_lambda` for freevar renaming
- `rounds/012/work/recover.py` - added `ClosureUnwrapper` and `FreevarResolver` to pipeline

## Files created

- `rounds/012/recovered/trivial/factorial.py`
- `rounds/012/recovered/trivial/fizzbuzz.py`
- `rounds/012/recovered/trivial/binary_search.py`
- `rounds/012/recovered/medium/text_stats.py`
- `rounds/012/recovered/medium/todo_cli.py`
- `rounds/012/recovered/hard/csvkit/__init__.py`
- `rounds/012/recovered/hard/csvkit/__main__.py`
- `rounds/012/recovered/hard/csvkit/formatter.py`
- `rounds/012/recovered/hard/csvkit/parser.py`
- `rounds/012/recovered/hard/csvkit_main.py` (consolidated single-file version)
