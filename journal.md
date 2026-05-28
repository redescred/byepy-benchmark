# byepy obfuscation journal

---

## Round 9 — 2026-05-27

### Techniques applied
- All round 8 techniques retained
- SHA-256 dead code predicates: dead branches now use `__import__('hashlib').sha256(str(var).encode()).digest()[:N] == b'\x00'*N`. Always False in practice (SHA-256 never produces all-zero prefix) but unprovable by any static analysis tool without cryptographic oracle access. Replaces NaN-identity (`x != x`) as the primary predicate — NaN is still present as a secondary candidate.
- Multi-statement dead bodies: each dead branch body contains 2-4 statements (assignments + raises + conditional raises) instead of a single `pass`/`return`. Bodies reference plausible variable names and look like real error-handling code, so a deobfuscator that cannot prove the predicate dead will retain the entire block in the recovered output.
- Injection density raised to 90% (was 75%): ~2x the dead block count per function, especially visible in medium/hard files (text_stats: 34 if-nodes vs 20 in round 8).

### What the deobfuscator did
<!-- TBD -->

### Judge scores
| Tier | Behavioural | AST sim | Readability | Passed? |
|------|------------|---------|-------------|---------|
| trivial | <!-- --> | <!-- --> | <!-- --> | <!-- --> |
| medium | <!-- --> | <!-- --> | <!-- --> | <!-- --> |
| hard | <!-- --> | <!-- --> | <!-- --> | <!-- --> |

### Why it failed / succeeded
<!-- TBD -->

### What to try next (Round 10)
<!-- TBD -->

---

## Round 8 — 2026-05-27

### Techniques applied
- All round 7 techniques retained
- `_c` integer constant table: every integer constant `|v| >= 2` in the code object is replaced with `_cv[key]` where the table is built in Stage 2 source. Builtins were already dispatched through `_ft[key]`; now the dispatch keys themselves are hidden inside `_c`. All integer literals — including the `_ft` keys — become double subscripts `_ft[_c[key]]` in the bytecode.
- User function trampolining: every top-level user-defined function is inserted via a trampoline pattern (`def _tmp_HASH(...): ...; _ft[key] = _tmp_HASH; del _tmp_HASH`). After this, all function calls — both builtins and user functions — go through `_ft`. `dis` output contains no readable function names; only `_ft[_c[k]]` subscript patterns.
- AnnotationStripper retains class-level `AnnAssign` (needed for `@dataclass` field discovery); strips only function parameter and return annotations.

### What the deobfuscator did
Static extraction as before (bypass anti-trace by reading keys from source AST). The agent built a custom Python 3.14 bytecode decompiler (1156 lines) since no off-the-shelf tool supports 3.14. Key steps: stage1_decode → stage2_decode (parsing both `_ft` and `_c` table entries from Stage 2 source assignments) → decompile code object using the custom decompiler → substitute double subscripts `_ft[_c[key]]` → decode XOR strings → remove NaN-trap dead code → undo CFF.

### Judge scores
| Tier | Behavioural | AST sim | Readability | Passed? |
|------|------------|---------|-------------|---------|
| trivial | PASS | 0.69/0.81/0.92 | n/a (names unreadable) | yes |
| medium | PASS | 0.83/0.78 | n/a (names unreadable) | yes |
| hard | PASS | 0.80 | n/a (names unreadable) | yes |

### Why it failed
The `_c` table is built in Stage 2 source as plain Python assignments (`cv_varname[key] = value`). The deobfuscator parsed Stage 2 as Python source with `ast.literal_eval` to extract both `_ft` and `_c` in one pass — the same technique used to extract `_ft` in round 7. Building a custom Python 3.14 decompiler (1391 lines) took significant time but ultimately succeeded for all corpus patterns. Once the double-subscript `_ft[_c[key]]` chain was resolved via table lookup, the rest of the pipeline (XOR string decode, NaN-trap removal, CFF unflattening, trampoline collapse) carried over unchanged from round 7. The recovered code has fully scrambled variable names (`Ib0e0320098aebf54`, `func_16455`) making it low-readability, but behavioral and structural checks both pass.

### What to try next (Round 9)
1. **SHA-256 dead code predicates**: Replace NaN-identity dead code with `sha256(str(var).encode()).digest()[:4] == b'\x00\x00\x00\x00'`. Always False but unprovable without cryptographic reasoning — breaks pattern-matching deobfuscators that look for `x != x`.
2. **Multi-statement dead bodies**: 2-4 statements per dead branch (assignments + raises) instead of a single `return`/`pass`. Deobfuscators that keep dead code inflate AST similarity and readability scores significantly more.
3. **Injection density raised to 90%** (was 75%): ~2x the dead code density in longer functions.

---

## Round 7 — 2026-05-27

### Techniques applied
- All round 6 techniques retained
- AnnotationStripper: strips all function parameter/return annotations. In Python 3.14 (PEP 649), annotated functions emit `__annotate__` lambdas that map each obfuscated arg name to its type, leaking the type information. Stripping kills that leak without breaking `@dataclass` (class-level AnnAssign is preserved).
- Per-position varying XOR for string encoding: key byte = (K + i*7 + 3) & 0xFF instead of constant K. Breaks single-byte key extraction tools; `bytes.fromhex()` instead of base64 changes the bytecode pattern.
- Dispatch table moved out of code object: `_ft` is built in Stage 2 bootstrap source, not in the module-level code. dis output no longer shows table-construction opcodes.
- Context-sensitive opaque dead code: predicates reference real local variables and look like defensive checks (`if result < -1: return result` after `result = 0`). Harder to prove dead without value-range tracking.
- Fixed label-collision bug: CFF `flatten_function` now uses `rng.sample(range(1000, 65536), n)` for unique labels. Old XOR-chaining in the 0-255 range caused ~63% collision probability at n=17+ states, silently skipping CFF cases.

### What the deobfuscator did
Static extraction as before. Parsed stage 1 for _D/_K, decrypted to get stage 2 source, read the dispatch table entries directly from stage 2 source (they are explicit Python assignments), extracted _D2/_K2, called `marshal.loads()` directly. Recovered a string decode template from MAKE_FUNCTION bytecode (C, M, A constants + hex payload). The NaN-trap dead code (`if x != x: return x`) was identified as always-false and stripped. State-machine CFF in csvkit was traced manually. All files recovered completely.

### Judge scores
| Tier | Behavioural | AST sim | Readability | Passed? |
|------|------------|---------|-------------|---------|
| trivial | PASS | 0.88–0.92 | 9-10/10 | yes |
| medium | PASS | 0.82–0.88 | 9-10/10 | yes |
| hard | PASS | 0.795 | 9-10/10 | yes |

### Why it failed
Dispatch table moved to stage 2 source is trivially readable — the deobfuscator just parses the stage 2 Python source instead of the bytecode. Per-position XOR was decoded by extracting K, M, A from the generator lambda's bytecode constants and applying the same formula. Annotations gone: irrelevant since the deobfuscator already handles garbled variable names. Context-sensitive dead code was correctly identified as always-false by checking the NaN-identity property. The deobfuscator produced near-perfect reconstructions at 9-10/10 readability throughout.

### What to try next (Round 8)
Remove the last two readable signal sources from the code object: (1) integer constant values — all constants ≥2 become `_c[key]` lookups; (2) user-defined function names — every top-level function is trampolined into `_ft`, matching the existing builtin pattern. After round 8, dis output contains only `_ft[_c[k]]` subscript chains and `_c[k]` constant lookups — no readable names, no readable constants.

---

## Round 6 — 2026-05-27

### Techniques applied
- All round 5 techniques retained
- BuiltinDispatcher: ALL builtin references (print, range, len, isinstance, type, int, str, float, bool, list, dict, set, tuple, hasattr, getattr, setattr, vars, dir, sorted, reversed, enumerate, zip, map, filter, sum, min, max, abs, any, all, hash, id, repr, open, input, callable, iter, next, hex, oct, bin, chr, ord, format, eval, exec, compile, globals, locals, staticmethod, classmethod, property) replaced with `_ft[N]()` subscript calls
- `_ft` dict is itself obfuscated: integer keys (SHA-256 derived), string values decoded via XOR+base64 at module load time using `getattr(__import__('builtins'), ...)`
- `_ft` variable name scrambled with same l/I scheme as other names
- Effect: co_names in dis output no longer contains ANY readable builtin names; everything is subscript operations on a single opaque table

### What the deobfuscator did
Parsed stage 1 and stage 2 statically. Built 4 helper tools: `extract.py` (stage 1+2 decryption), `disasm.py` (recursive dis.dis), `decode_strings.py` (base64+XOR patterns), `decode_ft.py` (dispatch table reconstruction by walking MAKE_FUNCTION + XOR-constant + byte-tuple patterns). No code execution needed.

### Judge scores
| Tier | Behavioural | AST sim | Readability | Passed? |
|------|------------|---------|-------------|---------|
| trivial | PASS | 0.68–0.95 | 9-10/10 | yes |
| medium | PASS | 0.96–0.99 | 10/10 | yes |
| hard | PASS | 0.92 | 10/10 | yes |

### Why it failed
The dispatch table (`_ft`) was built inside the code object's dis output — the deobfuscator walked MAKE_FUNCTION opcodes and matched each with the XOR key and byte tuple, reconstructing the entire builtin name map. Once the map was known, every `_ft[N]` in the bytecode was a named builtin. Single-byte XOR key was extractable from a single lambda constant. Co_varnames still garbled but LLM reconstructed intent from opcodes.

### What to try next (Round 7)
Move _ft table construction out of the code object entirely (into stage 2 bootstrap). Use per-position XOR key: (K + i*7 + 3) & 0xFF — breaks single-byte extraction. Use `bytes.fromhex()` instead of base64 — changes the bytecode pattern a decode_strings.py can look for. Add context-sensitive opaque dead code using tracked variable values.

---

## Round 5 — 2026-05-27

### Techniques applied
- All round 4 techniques retained
- Two-stage bootstrap: Stage 1 is zlib+XOR, Stage 2 is lzma+XOR (double-layer compression, different algorithms per stage)
- Stage 1 anti-patch check: `type(_Z.decompress).__name__ != 'builtin_function_or_method'` (blocks Python-level patching of zlib)
- Package consolidation: entire csvkit package inlined into `__main__.py` as a single bootstrap; other files (`__init__.py`, `parser.py`, `formatter.py`) become `# stub` comments; `_strip_main_guards()` removes `if __name__ == "__main__":` blocks from non-main files before inlining

### What the deobfuscator did
Parsed _D and _K from both stages statically, decrypted without executing any code (avoiding the anti-trace checks). Called `marshal.loads()` directly (not via bootstrap) to get the code object. Ran `dis.dis()` recursively and used LLM inference from bytecode. Still managed to recover logic despite co_varnames being l/I garbage — LLM reconstructed intent from the instruction patterns and constant values. Package: couldn't inline-detect it was consolidated but found all the class definitions inside the single __main__.py bootstrap.

### Judge scores
| Tier | Behavioural | AST sim | Readability | Passed? |
|------|------------|---------|-------------|---------|
| trivial | PASS | 0.68–0.95 | 8-10/10 | yes |
| medium | PASS* | 0.96–0.99 | 8-9/10 | yes |
| hard | PASS | 0.92 | 8-9/10 | yes |

*todo_cli individual file had a priority-mapping regression (recovered code used wrong priority symbol), but tier-level pass counted it as a pass. Lowest readability was 8/10.

### Why it failed
Static key extraction defeated everything. _D and _K (and _D2, _K2 for stage 2) are visible literals in the bootstrap source. Any deobfuscator that reads the source can reproduce the decryption without running any code. Anti-trace and anti-patch checks are irrelevant against purely static analysis. Co_varnames scrubbing slowed LLM inference but dis output still contains enough structural signal (BINARY_OP types, COMPARE_OP operands, constant values) for reconstruction. Package consolidation was helpful but the deobfuscator found all the code in one place.

### What to try next (Round 6)
Remove semantic anchors from co_names. In dis output, builtins like `print`, `range`, `len` are the most useful semantic anchors — they name what a function _does_. Replace all builtin references with `_ft[N]` where `_ft` is an opaque dispatch table populated at runtime. Then co_names in dis shows `_ft` (opaque subscript) instead of `print`, `range`, `len`, etc.

---

## Round 4 — 2026-05-27

### Techniques applied
- All round 3 techniques retained
- ctypes-based marshal: replaced `marshal.loads()` with `ctypes.pythonapi.PyMarshal_ReadObjectFromString(data, len)` — this is a direct C-level call, not a Python attribute that can be monkey-patched
- Anti-trace: `if sys.gettrace() is not None or sys.getprofile() is not None: raise SystemExit(1)` inserted at bootstrap entry
- co_varnames/co_freevars/co_cellvars scrubbing: post-compilation code-object walk replaces all local variable names with l/I garbage (preserving parameter names so keyword arguments still work)
- co_name scrubbing: all function names set to `<lambda>` (module remains `<module>`)
- Scrambled CFF: XOR-computed non-sequential state labels, shuffled elif order in the dispatcher

### What the deobfuscator did
The original deobfuscator agent stalled (appeared idle for ~1 hour). Spawned two fresh parallel replacement agents (one for medium, one for hard). They extracted _D and _K statically from the bootstrap source, decrypted to get the ctypes-using Stage 2, then called `marshal.loads()` in their own process on the decrypted bytes (anti-patching is irrelevant if you never execute the bootstrap). AST similarity dropped: factorial hit 0.65 (very close to the 0.6 threshold), fizzbuzz 0.82, binary_search 0.93, text_stats 0.81, todo_cli 0.94, csvkit 0.91.

### Judge scores
| Tier | Behavioural | AST sim | Readability | Passed? |
|------|------------|---------|-------------|---------|
| trivial | PASS | 0.65–0.93 | 9-10/10 | yes |
| medium | PASS | 0.81–0.94 | 9-10/10 | yes |
| hard | PASS | 0.91 | 9-10/10 | yes |

### Why it failed
Static extraction still worked. The deobfuscator never needed to execute the anti-trace or ctypes path — it decrypted statically and called marshal.loads directly. Co_varnames scrubbing hurt reconstruction (factorial dropped to 0.65) but LLM inference from constant values and opcode patterns bridged the gap. CFF scrambling added noise but a linear forward-only dispatch graph is always unrollable. Readability stayed 9-10/10 because the deobfuscator produced well-structured code.

### What to try next (Round 5)
Two-stage bootstrap (zlib outer, lzma inner) doubles the static work. Stage 1 type-check blocks Python-level patching of zlib.decompress. Most importantly: consolidate the csvkit package into a single bootstrap — pack all four files into one so the deobfuscator cannot analyse modules independently.

---

## Round 2 — 2026-05-27

### Techniques applied
- Scope-aware local variable + parameter renaming per function (l/I combos, not just module-level)
- Dead code injection: random always-false branches with list/dict operations
- Opaque predicates: `if (x**2 >= 0):` style always-true guards around real code
- XOR + base64 string encoding (more complex than pure base64 from round 1)
- Module-level function renaming retained from round 1

### What the deobfuscator did
Identified XOR+base64 pattern, decoded all strings. Stripped dead code (always-false guards trivially identified as `abs(-1) < 0`, `id(None) != id(None)`, etc.). Read XOR key from literal in source. Variable renaming produced meaningless names but the LLM recovered semantics from context. Full 9-10/10 readability recovery.

### Judge scores
| Tier | Behavioural | AST sim | Readability | Passed? |
|------|------------|---------|-------------|---------|
| trivial | PASS | PASS | 9-10/10 | yes |
| medium | PASS | PASS | 9-10/10 | yes |
| hard | PASS | PASS | 9/10 | yes |

### Why it failed
Dead code patterns were stereotyped (same list/dict operations repeated). XOR key was a visible literal. Opaque predicates were obvious (`abs(-1) < 0` is trivially false). Docstrings from round 1 were recovered from encoded strings and gave away full function intent. AST structure unchanged enough for high similarity.

### What to try next (Round 3)
Add bytecode-level obfuscation. Compile the AST-obfuscated code with `compile()`, then manipulate the code object directly (co_varnames scrubbing, co_name scrubbing), serialize with `marshal.dumps()`, compress with zlib, and execute via a bootstrap. This makes decompilers (uncompyle6, pycdc) the primary attack surface rather than source-level AST analysis. Add CFF (control flow flattening) using a while-True state machine dispatcher.

---

## Round 1 — 2026-05-27

### Techniques applied
- shake_128 module-level function name renaming (salt `byepy-r1:<filename>`)
- base64 string literal encoding (skipping f-string inner constants)

### What the deobfuscator did
- Identified the shake_128 pattern and reconstructed the salt from the obfuscated names
- Decoded all base64 strings directly
- Produced byte-identical output

### Judge scores
| Tier | Behavioural | AST sim | Readability | Passed? |
|------|------------|---------|-------------|---------|
| trivial | PASS | PASS | 10/10 | yes (deobf won all checks) |
| medium | PASS | PASS | 9/10 | yes |
| hard | PASS | PASS | 9/10 | yes |

### Why it failed
The salt was discoverable from first principles. The deobfuscator recomputed it. String encoding was single-layer and trivially reversible. AST structure unchanged — PYLINGUAL would have handled even without the salt.

### What to try next (Round 2)
Dead code injection + opaque predicates are the highest-leverage next move because:
- They ADD nodes to the AST, degrading the AST similarity score even if structure is partially recovered
- Readability drops if there are many fake branches and variables
- XOR + base64 string encoding is harder to spot as a single reversible pattern
- Local variable renaming (scope-aware per function) will hurt readability even if function names are recovered
- Control flow flattening would be ideal but is complex to implement correctly; defer to round 3

Round 2 plan:
1. Scope-aware local variable + parameter renaming per function
2. Dead code injection: random always-false branches with plausible-looking code
3. Opaque predicates: wrap real code in `if (x**2 >= 0):` style always-true guards
4. XOR + base64 string encoding (harder to spot as a pattern than pure base64)
5. Keep module-level function renaming

---

## Round 3 — 2026-05-27

### Techniques applied
- DocstringStripper (all docstrings removed — no hints)
- ScopeAwareRenamer (module-level functions + all locals renamed to l/I combos)
- DeadCodeInjector (always-false branches between statements)
- XorStringEncoder (XOR+base64 inline decode expressions)
- CFFTransformer (linear functions wrapped in while-True state machine dispatcher)
- marshal+zlib+XOR bootstrap for single files (using `getattr(__import__('builtins'),'exec')`)
- Package files: AST-only (relative imports need package context)

### What the deobfuscator did
Single files: monkey-patched `marshal.loads` before executing the bootstrap. Captured the code object, ran `dis.dis()`, reconstructed source from bytecode. Python 3.14 was not an obstacle — co_varnames still contained the (shortened) renamed identifiers; LLM read the dis output and inferred intent. Full 9-10/10 recovery.

Package: read XOR key directly from the literal expression in source, decoded strings in a loop, stripped dead code (always-false guards trivially identified), unrolled the CFF dispatcher. Straightforward.

### Judge scores
| Tier | Behavioural | AST sim | Readability | Passed? |
|------|------------|---------|-------------|---------|
| trivial | PASS | 0.92-0.95 | 9-10/10 | yes |
| medium | PASS | 0.95-0.97 | 9/10 | yes |
| hard | PASS | 0.98 | 8-10/10 | yes |

### Why it failed
1. `marshal.loads` is a Python-level attribute on a built-in module. It can be replaced before the bootstrap runs — the bootstrap then calls our patched version.
2. co_varnames in the compiled code object retained the renamed identifiers. Even short l/I names are enough for an LLM to reconstruct logic from dis.
3. CFF was a single linear dispatch chain. All state transitions were forward-only, making unrolling trivial.
4. Dead code patterns (list operations, empty dict updates) were stereotyped and easy to spot.

### What to try next (Round 4)
1. **ctypes-based marshal**: call `ctypes.pythonapi.PyMarshal_ReadObjectFromString` directly instead of `marshal.loads`. Defeats module attribute patching.
2. **co_varnames total scrub**: after compiling, walk ALL code objects recursively and replace co_varnames, co_freevars, co_cellvars with indistinguishable l/I strings. Dis output becomes noise.
3. **Anti-trace**: check `sys.gettrace() is not None` at bootstrap entry and raise SystemExit. Defeats sys.settrace-based extraction.
4. **Opaque CFF with back-edges**: add non-linear state transitions and multiple exit states so the dispatch graph is not a simple sequence.
5. **More realistic dead code**: dead branches should contain plausible business logic (partial computations that reference real variables) rather than stereotyped patterns.
6. **Deeper variable rename**: also rename class-level attributes that aren't accessed externally.

---

Append-only. Each round adds a block below. Most recent at top.

---

## Pre-round notes (2026-05-27)

Autoresearch completed. Key threat model: PYLINGUAL (syssec-utd/pylingual, BlackHat 2024) achieves 87% accuracy on unobfuscated Python 3.9-3.12. The deobfuscator subagent also has: sandbox execution, dis module, uncompyle6/pycdc, arbitrary shell.

Planned ladder (from research):
1. Variable renaming + base64 string encoding (Tier 1, AST-level — will be trivially recovered)
2. Control flow flattening (state machine dispatcher)
3. Dead code injection + opaque predicates
4. Marshal wrapping + zlib
5. AES-256-CBC bytecode encryption
6. co_varnames scrubbing + redundant opcodes
7. Custom opcode permutation (modified CPython)
8. Compound custom opcodes (Quarkslab technique)

Key insight from research: anything that preserves standard Python bytecode is recoverable by PYLINGUAL or an LLM reading dis output. Techniques only become robust at Tier 3 (custom opcode remapping) where the .pyc is unreadable without the custom opcode table. Tier 2 (marshal/encryption wrapping) fails because dynamic sandbox execution can always dump the inner bytecode via a hook on the runtime loader.

Starting with Tier 1 to establish the loop baseline.
