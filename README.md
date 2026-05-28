# byepy: adversarial Python obfuscation loop

A self-contained experiment in adversarial obfuscation. One agent obfuscates a fixed corpus of Python programs; a second agent, with no memory of how the obfuscator works, tries to recover them. Each round the obfuscator adapts to what the deobfuscator can handle. The loop runs until the deobfuscator fails every check across every tier of the corpus at the same time.

The loop ran for 16 rounds and the obfuscator ended up winning.

## Setup

The corpus has three tiers of increasing complexity:

| tier | files | total AST nodes |
|------|-------|-----------------|
| trivial | factorial.py, fizzbuzz.py, binary_search.py | 117 / 130 / 278 |
| medium | text_stats.py, todo_cli.py | 672 / 890 |
| hard | csvkit/ (4-file package) | 1746 |

Three scoring checks run on each file. The first is behavioural: the recovered file must produce byte-identical stdout to the original. The second is AST similarity: Jaccard similarity of node-type multisets between original and recovered source must be at least 0.6 (a score of 1.0 means perfect structural match; 0.6 means roughly 60% of the structure was recovered). The third is readability, an LLM judge with a 6/10 cutoff. Readability was not evaluated in most rounds and was treated as pass-by-default.

A round looks like this:

1. The obfuscator writes new obfuscated files to `rounds/NNN/obfuscated/`.
2. A fresh deobfuscator subagent is spawned with no memory of the obfuscator's design. It receives only the obfuscated files and the previous round's deobfuscation tools (`cleanup.py`, `decompiler.py`, `extract.py`, `recover.py`). It can read and modify those tools freely.
3. The subagent writes recovered files to `rounds/NNN/recovered/`.
4. `judge.py` scores them and writes `report_objective.json`.

The deobfuscator subagent is an LLM running without any external guidance about what the obfuscator did. It can inspect the obfuscated Python, trace bytecode, write test scripts, edit its pipeline. It just can't ask the obfuscator what changed.

## Round-by-round history

### Round 1: baseline (avg AST 1.000)

Simple AST pass: identifier renaming with `shake_128` and base64 string encoding. No bootstrap, no CFF, no dead code. The deobf response was trivial. A rename map and a base64 decoder. Full recovery in minutes.

### Round 2: dead code + scope-aware renaming (avg 0.995)

Added scope-aware local and parameter renaming (separate salt per function scope). Added dead code injection using `False` and `None is not None` as predicates. The deobf response was immediate: pattern-matched the `if False:` and `if None is not None:` blocks and stripped them. Renamed identifiers by grouping variables that appear together in the same assignment contexts.

### Round 3: CFF + marshal bootstrap (avg 0.955)

Added control flow flattening (CFF): linear functions are converted to a while-True state machine where a state variable `_sXX` is assigned an initial label, and each case updates the state variable to the next label before breaking or continuing. Added a single-stage bootstrap: the module source is compiled to a code object, marshal'd, zlib-compressed, XOR'd with a 16-byte key, and the result is a self-contained loader that calls `ctypes.pythonapi.PyMarshal_ReadObjectFromString`. Docstrings stripped.

`uncompyle6` and `decompyle3` both failed on the output (`pycdc` too). They expect specific CPython 3.x bytecode instruction sequences that do not appear after compilation under Python 3.14.

The deobf wrote a custom Python 3.14 bytecode decompiler from scratch (later grew to about 1400 lines). The bootstrap decryption was straightforward, since the XOR key and ciphertext are literal constants in the source. CFF was reversed by `CFFUnflatten`: detect `while True:` with a nested if-chain keyed on a state variable, map label-to-body, emit the bodies in label order.

### Round 4: two-stage bootstrap + co_varnames scrub (avg 0.846)

Two-stage bootstrap: Stage 1 decrypts (zlib+XOR) to Stage 2 source, which decrypts (lzma+XOR) to the actual code object. `scrub_code()` replaces `co_varnames`, `co_cellvars`, `co_freevars`, and `co_name` with `shake_128`-derived garbage using independent salts per slot type. Local variable names in the disassembly look like `lIllIlIlIlIlIlI`. An anti-trace guard (`sys.gettrace() is not None: raise SystemExit(1)`) prevents running under a debugger.

The deobf read both decrypt stages from the source AST (no exec needed; key and ciphertext are literals). Built `FreevarResolver` to recover original freevar names by tracing `SET_FUNCTION_ATTRIBUTE` bytecode sequences and correlating the cell objects being captured. Scores dropped to 0.65 on factorial. The smallest file is most sensitive to any surviving noise.

### Round 5: builtin dispatch table + package consolidation (avg 0.909)

Every builtin reference (`print`, `range`, `len`, `isinstance`, all of them) replaced with `_ft[N]`, where `_ft` is a dispatch dict keyed by stable SHA-256-derived integers. The dict is built in Stage 2 source using `getattr(__import__('builtins'), ...)` with XOR-encoded name strings. The entire csvkit package (four .py files) is concatenated and obfuscated as a single unit; relative imports are stripped.

The deobf parsed Stage 2 source to extract the dispatch table. Wrote `decode_ft.py` to walk the `MAKE_FUNCTION` + XOR-constant patterns in the bytecode. All files recovered.

(`todo_cli.py` failed the behavioural test this round because of a dispatch table bug in the priority-display logic. The obfuscated version rendered priority markers incorrectly. Fixed in round 6.)

### Round 6: user-function trampolines + XOR string encoder (avg 0.878)

User-defined top-level functions trampolined into `_ft`: each function definition becomes `def _tmp_HASH(args): body; _ft[key] = _tmp_HASH; del _tmp_HASH`. After this, all calls (builtins and user functions alike) go through `_ft[key](...)`. `co_names` contains nothing readable.

Per-position varying XOR for string encoding: key byte for position `i` is `(K + i*7 + 3) & 0xFF` instead of a constant, which breaks tools that extract a single-byte XOR key.

The deobf added `TrampolineCleanup` to collapse `def _tmp; _ft[k] = _tmp; del _tmp` back into `def func_NNNNN`. Added `XorStringDecoder` with the per-position formula. It had to figure out the formula by reading the bootstrap XOR generator expression, which is a literal in the source.

### Round 7: annotation stripping + scrambled CFF (avg 0.849)

`AnnotationStripper`: strips all function parameter and return annotations. Python 3.14 (PEP 649) compiles annotated functions with `__annotate__` lambdas that map each parameter name to its type. Leaving annotations in would expose the original parameter names through the annotation lambda even after variable renaming.

Scrambled CFF: labels are now sampled from a wide range (1000 to 65535) and the if-chain cases are shuffled, so the textual order of `if sv == LABEL:` blocks has no relation to execution order.

The dispatch table is moved from the code object into Stage 2 bootstrap source, so `dis` output contains no table-construction opcodes.

The deobf added `ScrambledCFFUnflatten` to handle the shuffled label variant (build a label-to-body map, then emit in state-machine execution order). Annotation stripping was irrelevant to recovery; names were already garbled.

### Round 8: integer constant table (avg 0.804)

Every integer constant `|v| >= 2` in the obfuscated source replaced with `_c[key]`, where the table is built in Stage 2 bootstrap. Stage 2 XOR becomes position-dependent: `key[i%16] ^ ((i>>4) & 0xFF)` instead of `key[i%16]`. The `_ft` and `_c` tables are built via loops over encoded triples and masked pairs rather than as individual assignment statements. That broke the Stage 2 AST-walk pattern the deobf had been using.

The deobf updated `extract.py` to parse the loop-based table constructions (`_parse_ft_loop`, `_parse_c_loop`). Handled the position-dependent Stage 2 XOR. Integer constant restoration added as a cleanup pass.

### Round 9: SHA-256 dead predicates + multi-statement bodies (avg 0.814)

SHA-256 dead-code predicates: dead branches use `sha256(str(var).encode()).digest()[:N] == b'\x00'*N`. SHA-256 never produces an all-zero prefix, so the branch is always dead. But this cannot be proven by pattern-matching or `ast.literal_eval`. The deobf needs cryptographic reasoning or explicit knowledge that SHA-256 is preimage-resistant.

Dead block bodies expanded to 2-4 statements (assignments, raises, conditional raises that reference plausible local variables) so they look like real error handling at a glance.

The deobf added `_is_sha256_dead_test` to match the structural form `hashlib.sha256(str(VAR).encode()).digest()[:N] == b'\x00'*N`. It matched by recognising the call chain rather than by evaluating the expression, which was the right call. Added `_is_algebraic_dead_test` for the modular-arithmetic families introduced in round 10.

### Round 10: stage 2 as code object + try/except wrappers (avg 0.806)

Stage 1 now produces a marshal'd code object rather than Stage 2 source text. The deobf must decompile Stage 2 before it can extract `_ft` and `_c`. Transparent `try: <body> except BaseException: raise` wrappers added around every function body. Semantically inert. They produce CPython 3.14 exception-table bytecode that the decompiler couldn't yet handle. Stage 1 XOR changed to `(i*7+13) & 255`.

The deobf updated `stage1_decode` to detect the marshal case and decompile before proceeding. Added `TryExceptUnwrapper` to strip the transparent wrappers. Decompiler patched for exception-table handling (COPY/POP_EXCEPT patterns in CPython 3.14).

### Round 11: no obfuscation change (avg 0.839)

The deobf agent's csvkit recovery produced wrong stdout because the previous round's exception-table decompiler fix was incomplete. The `_if_else` handler was cutting the else branch short when a JUMP_BACKWARD appeared mid-branch. No new obfuscation this round.

The deobf diagnosed the behavioural failure by diffing original vs recovered output line by line. Found the `_if_else` early-return bug, patched it. Added stack snapshot handling for the else-branch path. csvkit passed. Scores ticked up slightly.

### Round 12: ClosureCaptureTransformer (avg 0.843)

Every function's last `return EXPR` rewritten to a triple-nested closure:

```python
_cl1234 = EXPR
def _mid5678():
    def _inner9012():
        return _cl1234    # freevar, captured through two levels
    return _inner9012()
return _mid5678()
```

`scrub_code()` garbles `_cl1234` as it appears in four independently-salted slots: `outer.co_cellvars`, `_mid.co_freevars`, `_mid.co_cellvars`, `_inner.co_freevars`. After garbling, the inner function's freevar name has no visible binding in the outer scope, so calling it raises `NameError`.

Stage 1 XOR changed to `(i*7+13) & 255` (same formula; detection updated in extract.py).

This was one of the harder rounds for the deobf. The agent had to trace `SET_FUNCTION_ATTRIBUTE closure` bytecode sequences to build a per-function freevar rename map, then apply those renames during decompilation. `FreevarResolver` reads `BUILD_TUPLE` arguments preceding each closure-setting sequence and maps the child's `co_freevars[i]` to whatever name the outer scope uses for the corresponding cell variable. One name collision in csvkit (a genexp in `TableFormatter.format` used the same garbled name for two different captured values from two different scopes) required scoped resolution per code object rather than a single global map. The agent got this right.

### Round 13: lambda-default closure + four new dead families (avg 0.843)

The closure form changed to a lambda with a default argument:

```python
_cl1234 = EXPR
_f5678 = lambda _x9012=_cl1234: _x9012
return _f5678()
```

The default argument is evaluated at lambda creation time. No closure cell is created, `co_freevars` is empty, `SET_FUNCTION_ATTRIBUTE(closure)` is never emitted. `FreevarResolver` has nothing to trace. The previous `ClosureUnwrapper` pattern (detect Assign/FunctionDef/Return triplet) failed on this form because the FunctionDef was replaced by a lambda assignment.

Four new dead-code predicate families added: banker's rounding (`round(0.5) != 0`, always False in Python 3's round-half-to-even), abs/divmod invariants (`abs(-N) > N`, `divmod(A,B)[0] != A//B`), chr/ord round-trips (`ord(chr(N)) != N`), int-construction predicates (`int(True) != 1`). Stage 1 XOR changed to `(i*11+7) & 255`.

The deobf updated `ClosureUnwrapper` to detect the lambda-default form (Assign + lambda with one default arg). Added four new `_is_X_dead_test` functions. Round went cleanly; scores unchanged.

### Round 14: triple-nested def + computed-constant predicates (avg 0.842)

Closure returned to triple-nested def (from round 12) but with three levels instead of two. `_cl1234` now appears in four name slots. `_mid` has two statements (the inner def and the return call), so `ClosureUnwrapper`'s `len(s1.body) == 1` guard failed. The previous unwrapper expected a one-statement `_mid` body.

Computed-constant dead predicates: `sum(range(N)) != K` (Gauss formula gives the expected sum), `max([...]) != K`, `min([...]) != K`, `sorted([...]) != [...]`, `list(reversed([...])) != [...]`. These require executing Python to evaluate; `ast.literal_eval` cannot handle them.

Stage 1 XOR changed to `(i*13+11) & 255`.

The deobf patched the `len(s1.body)` guard to accept 2-statement `_mid` bodies. Added `_is_computed_const_dead_test`, which calls `ast.literal_eval` on the list literals in the sort/max/min/reversed forms and compares against the embedded constant. This worked because the list literals are constant after `_c` substitution. The sum/range form required recognising `sum(range(N))` as `N*(N-1)//2`. Both handled correctly.

### Round 15: bitwise identity + value-anchored quadratic (avg 0.843, stalled)

Family 10, bitwise identity predicates using tracked integer variables:

```
(n & ~n) != 0        # n AND complement is always 0
(n ^ n) != 0         # n XOR n is always 0
(n | ~n) != -1       # n OR complement is always -1 (all bits set)
```

These contain a Name node, so `ast.literal_eval` fails. The deobf has to match them structurally.

Family 11, value-anchored quadratic predicates. If a variable `n` is known to equal `v` at the insertion point, then `(n - v) * (n - v)` is always 0, so `(n - v) * (n - v) != 0` is always False. Removing this requires constant propagation: trace the assignment `n = v` in the same statement block and use the known value to evaluate the expression.

Dead-code density raised to 3 blocks per gap. Stage 1 XOR changed to `(i*17+3) & 255`.

The round stalled. Due to a process error, the deobf agent was given round 015's cleanup.py (the one that already contained `_is_bitwise_identity_dead_test`, `_is_value_anchored_dead_test`, and `ValueAnchoredDeadRemover`) before the obfuscated round 015 files were produced. The agent had no work to do. Scores held at 0.843, identical to rounds 12-14.

This exposed the core problem: every round since 12, the average AST score had barely moved (0.803, 0.814, 0.806, 0.839, 0.843, 0.843, 0.842, 0.843), and the obfuscator was clearly running in place.

### Why scores plateaued at 0.84

`DeadCodeRemover` has two removal paths.

Path 1, `_is_dead_test(PRED)`: if the predicate is structurally recognised as always-False, the whole block goes away regardless of what the body contains.

Path 2, `_matches_other_dead_check(node)`: handles bounds-check predicates (`x < 0`, `x > NNN`, `len(v) > NNN`). Removes the block only if `_dead_body_only(BODY)` also returns True.

`_dead_body_only` returns False if the body contains any `if` statement. Only one of the four body templates (Template 2) contained an `if`. So roughly 75% of bodies trivially passed the body check and bounds-check blocks were removed. But bounds-check predicates made up only about 15% of the candidate pool. Combined: survival rate for bounds-check blocks was around 25% * 15% ≈ 4%. With 3 blocks per gap, that is about 0.12 surviving blocks per gap.

For every other family, the whole block was removed via path 1 as soon as the agent added a structural matcher. Adding a matcher is a small, well-scoped task: read the predicate form, write a function that recognises it, plug it into `_is_dead_test`. The agent never failed to do that.

The real problem was the asymmetry. The obfuscator was in a cat-and-mouse game it structurally could not win. Every new predicate family was solvable because the predicates were mathematically fixed invariants of some kind (algebraic identities, cryptographic preimage-resistance, and a few type-system rules), and the deobf agent could write a new case in an existing pattern-matching function for each one.

### Round 16: the kill shot (avg 0.247, loop terminates)

The insight: stop playing the predicate game entirely. Both removal paths check the predicate. Path 1 recognises specific forms; path 2 requires a specific predicate shape plus a simple body. Use predicates that neither path handles.

Looking at `_is_dead_test` from the round 015 cleanup, it had 13 named cases: `_is_sha256_dead_test`, `_is_algebraic_dead_test`, `_is_isinstance_dead_test`, `_is_sys_dead_test`, `_is_banker_rounding_dead_test`, `_is_abs_divmod_dead_test`, `_is_chr_ord_dead_test`, `_is_int_construction_dead_test`, `_is_computed_const_dead_test`, `_is_bitwise_identity_dead_test`, `_is_value_anchored_dead_test`, plus the base cases for `False` and `None is not None`.

None of those 13 cases handled `issubclass` predicates. None of them touched `callable` or `bytes` either.

Three new candidate families went in. Family 12 used `issubclass` always-False pairs. Python's type hierarchy guarantees that things like `issubclass(int, str)`, `issubclass(list, dict)`, or `issubclass(float, int)` are always False. `issubclass(A, B)` calls have three names in the source (the function name and the two type arguments) and all of them are in `_DISPATCH_TARGETS`, so they survive `_ft[K]` substitution and appear as their original names after deobfuscation. 12 predicates total.

Family 13 used `not callable(BUILTIN)`. All Python builtins are callable objects, so `not callable(print)`, `not callable(len)`, and so on are always False. `callable` is in `_DISPATCH_TARGETS`. 20 predicates total.

Family 14 used `bytes(N)` invariants. `len(bytes(4)) != 4` is always False (bytes(N) produces N zero bytes). `bytes(4) != bytes(4)` is always False (equal content). 7 predicates total.

All four dead-body templates were updated to contain an `if` statement. This makes `_dead_body_only()` return False for every body. So even if the agent adds a new path-2-style matcher for one of the other families, the body check stops the block from being removed.

Block density was raised from 3 to 5 per gap.

The deobf starting point was round 014 cleanup.py (not 015), which forced the agent to rediscover families 10 and 11 from scratch in addition to encountering 12, 13, and 14 for the first time.

Result: a 100% block survival rate, with neither removal path touching any block.

| file | original nodes | recovered nodes | AST score |
|------|----------------|-----------------|-----------|
| factorial.py | 117 | 512 | 0.219 |
| fizzbuzz.py | 130 | 373 | 0.327 |
| binary_search.py | 278 | 771 | 0.352 |
| text_stats.py | 672 | 3004 | 0.213 |
| todo_cli.py | 890 | 4492 | 0.191 |
| csvkit (pkg) | 1746 | 9078 | 0.182 |

Every tier passed behavioural (dead branches never execute) and every tier failed AST (all scores below 0.6), so the loop terminated on this round.

## Full score history

| round | factorial | fizzbuzz | binary_search | text_stats | todo_cli | csvkit | avg |
|-------|-----------|----------|---------------|------------|----------|--------|-----|
| 001 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 002 | 1.000 | 1.000 | 1.000 | 0.975 | 1.000 | 0.997 | 0.995 |
| 003 | 0.919 | 0.954 | 0.954 | 0.953 | 0.974 | 0.979 | 0.956 |
| 004 | 0.650 | 0.823 | 0.932 | 0.814 | 0.943 | 0.912 | 0.846 |
| 005 | 0.684 | 0.954 | 0.941 | 0.964 | 0.992 | 0.916 | 0.909 |
| 006 | 0.880 | 0.803 | 0.928 | 0.798 | 0.951 | 0.911 | 0.879 |
| 007 | 0.880 | 0.803 | 0.918 | 0.823 | 0.878 | 0.795 | 0.850 |
| 008 | 0.689 | 0.812 | 0.918 | 0.830 | 0.778 | 0.799 | 0.804 |
| 009 | 0.689 | 0.812 | 0.918 | 0.812 | 0.872 | 0.782 | 0.814 |
| 010 | 0.689 | 0.812 | 0.918 | 0.816 | 0.818 | 0.785 | 0.806 |
| 011 | 0.874 | 0.812 | 0.918 | 0.818 | 0.818 | 0.792 | 0.839 |
| 012 | 0.874 | 0.832 | 0.918 | 0.818 | 0.819 | 0.799 | 0.843 |
| 013 | 0.874 | 0.832 | 0.918 | 0.820 | 0.819 | 0.799 | 0.843 |
| 014 | 0.874 | 0.832 | 0.918 | 0.818 | 0.819 | 0.792 | 0.842 |
| 015 | 0.863 | 0.832 | 0.918 | 0.820 | 0.819 | 0.804 | 0.843 |
| **016** | **0.219** | **0.327** | **0.352** | **0.213** | **0.191** | **0.182** | **0.247** |

Rounds 5 and 11 had behavioural failures (`todo_cli.py` and `csvkit` respectively) on top of the AST scores shown.

## The deobfuscator as an agent

A few observations on how the deobf agent behaved across rounds.

The agent never gave up on a round and every round it produced recovered files for all six targets. Round 12 was the most complex and required custom bytecode tracing to resolve freevar name conflicts across scopes, and the agent still produced correct output there.

It rarely hallucinated technique details. When it needed to understand a new construct, it read the obfuscated bytecode directly via `dis.dis` and inspection of code-object slots like `co_consts`, rather than assuming it knew what the obfuscator had done. The deobf notes from round 6 describe how the agent traced the dispatch table construction from the bytecode before writing `decode_ft.py`.

The one significant mistake it made was in round 11 (the csvkit behavioural failure), where the fix required understanding that `_if_else` in the decompiler was exiting the else-branch early when it encountered `JUMP_BACKWARD`. The agent initially diagnosed this as a dead-code issue and thought some else-branch statements were being misidentified as dead. After two failed attempts produced the same wrong output, it read the decompiler source more carefully and found the actual bug in the return-value threading through `_if_else`, which took longer than the other rounds but worked out in the end.

Structural matching was its default approach, and it was correct to use it. Each predicate family the obfuscator introduced had a distinct structural signature. SHA-256 predicates look like a chain of attribute calls on a bytes result. Algebraic predicates are BinOp(Mod, Eq, Const). Bitwise identity is BinOp(BitAnd, ~Name, Ne, 0). The agent wrote one recogniser per family and chained them in `_is_dead_test`. That approach is efficient as long as the obfuscator keeps adding new families. It stops working when the obfuscator uses a family that looks like nothing in the function.

The plateau between rounds 12 and 15 (avg 0.843) showed the agent reaching a local optimum. It was removing all structurally-recognisable dead code but couldn't go further. The remaining AST difference came from scrambled variable names rather than from dead code, and the agent's renamer was already near-optimal.

Round 16 was the round the agent did not see coming. The deobf was given round 014 cleanup.py as its starting point and the first thing it would have done is run the pipeline on the new obfuscated files. It would have seen the AST scores collapse to 0.2-0.35 and looked at the recovered output to understand what survived. At that point it would see blocks like `if issubclass(int, str): ...` and `if not callable(print): ...` scattered through the file, and it would need to add matchers for those forms. Whether it could do so fast enough to affect the round's score was never tested, since the loop terminates on what the initial run produces.

## What would break round 16's defence

If the game continued, the agent would write three new matchers into `_is_dead_test`:

```python
def _is_issubclass_dead_test(node):
    # match: issubclass(Name, Name) where the pair is in a known-false table
    ...

def _is_not_callable_dead_test(node):
    # match: UnaryOp(Not, Call(callable, [Name])) where Name is a known builtin
    ...

def _is_bytes_invariant_dead_test(node):
    # match: len(bytes(Const)) != Const  and  bytes(Const) != bytes(Const)
    ...
```

These are simple structural matchers and the agent would write them in the same style as the existing ones, so round 17 would end up looking a lot like round 9.

The next move would be predicates that require evaluating a callable rather than matching a static structure. `(lambda: False)()` is always False, but proving that requires evaluating a lambda. `any(x > x for x in range(10))` is always False (no integer satisfies `x > x`), but proving that requires evaluating a generator expression. `os.getpid() < 0` is always False on any real system (PIDs are non-negative), but proving that requires knowing the invariant about the OS API.

Or semantic transforms that change program structure in ways pattern-matching can't reverse:

- converting loops to recursive functions
- swapping conditionals for dispatch tables
- rewriting function bodies in continuation-passing style

A deobfuscator can't reverse those without understanding the original algorithm, and recognising specific bytecode patterns isn't enough to get there, which makes for a substantially harder target than anything the round 016 obfuscator throws.

## Repository layout

```
byepy/
  obfuscator.py            canonical obfuscator (round 16)
  corpus_meta.json         corpus file list with run_as and tier metadata
  judge.py                 objective scoring (behavioural + AST)
  run.py                   round scaffolding harness
  corpus/
    trivial/               factorial.py, fizzbuzz.py, binary_search.py
    medium/                text_stats.py, todo_cli.py
    hard/csvkit/           __init__.py, __main__.py, formatter.py, parser.py
  rounds/
    001/ ... 016/
      obfuscator.py        obfuscator snapshot for that round
      obfuscated/<tier>/   obfuscated files
      recovered/<tier>/    deobf agent output
      work/                deobf pipeline tools for that round
        cleanup.py         AST cleanup passes
        decompiler.py      custom Python 3.14 bytecode decompiler
        extract.py         stage 1+2 decryption
        recover.py         top-level recovery pipeline
      report_objective.json  judge scores
      deobf_notes.md       agent's notes (rounds 6-12)
```
