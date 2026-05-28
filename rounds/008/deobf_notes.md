# Round 008 deobfuscation notes

## Obfuscation scheme

Two-stage bootstrap. Stage 1 is a zlib-compressed, XOR-encrypted source string
that loads Stage 2. Stage 2 is an lzma-compressed, XOR-encrypted code object
plus two opaque lookup tables (`_ft` for builtins, `_c` for integer constants)
that are injected into the exec globals dict. The code object then runs with
those tables visible as globals so all builtin calls and meaningful integer
constants are routed through subscript indirection.

On top of that bootstrap, the AST-level transforms applied before compilation
are:

- Scoped identifier renaming to `l`/`I`-only soup
- Per-position-varying XOR + bytes.fromhex string encoding
- Context-sensitive dead-code injection (NaN-identity checks, impossible bound
  comparisons)
- Control-flow flattening via state-machine while True / if-elif chains
- User function trampolining: `def _tmp(...): ...; _ft[k] = _tmp; del _tmp`
- co_varnames scrubbing on compiled code objects
- Annotation stripping (PEP 649 lambdas killed) except for class-level
  AnnAssign (kept for dataclass)
- Package consolidation: csvkit becomes one bootstrap `__main__.py` plus stub
  `__init__.py`, `parser.py`, `formatter.py`

## Static extraction

`work/extract.py` walks Stage 1 and Stage 2 source via `ast.literal_eval`,
never executes the bootstrap. Pulls out:

- The marshal'd code object (lzma.decompress + 16-byte XOR)
- The `_ft` mapping {int_key -> builtin_name} from the Stage 2 lookup-table
  building lines (decoding each value's bytes.fromhex + varying XOR)
- The `_c` mapping {int_key -> int_value}
- The table variable names

## Custom Python 3.14 bytecode decompiler

`work/decompiler.py` (~2400 lines) implements a stack-machine walker for
Python 3.14 bytecode. Handles the opcodes observed in the round 8 corpus:

- All basic loads/stores including `LOAD_FAST_BORROW`, `LOAD_FAST_AND_CLEAR`,
  `STORE_FAST_LOAD_FAST`, `STORE_FAST_STORE_FAST`, `LOAD_FAST_LOAD_FAST`
- `LOAD_GLOBAL` and `LOAD_ATTR` with the bound-method `+ NULL|self` ABI
- `BINARY_OP`/`COMPARE_OP`/`IS_OP`/`CONTAINS_OP` plus subscript (BINARY_OP 26)
- `CALL`, `CALL_KW`, `CALL_FUNCTION_EX` with method-call collapse
- `BUILD_LIST/SET/MAP/CONST_KEY_MAP/TUPLE/SLICE` plus `LIST/SET/MAP_ADD`
- `FORMAT_SIMPLE`/`FORMAT_WITH_SPEC`/`FORMAT_VALUE`/`CONVERT_VALUE` + `BUILD_STRING`
- `IMPORT_NAME`/`IMPORT_FROM` to ast.Import/ImportFrom
- `LOAD_BUILD_CLASS` plus decorator chains to ast.ClassDef
- `MAKE_FUNCTION`/`SET_FUNCTION_ATTRIBUTE` to ast.FunctionDef (with closure,
  defaults, kw_defaults, annotations attributes)
- `RAISE_VARARGS`/`RERAISE`
- `LOAD_COMMON_CONSTANT` (3.14 specialization hint)

Structured constructs detected by pattern matching:

- For loops: `GET_ITER` + `FOR_ITER` + body + `JUMP_BACKWARD` + `END_FOR`/`POP_ITER`
- While loops: `POP_JUMP_IF_X` + body + `JUMP_BACKWARD` to the start of the
  condition's basic block (computed via `_find_cond_start`)
- If/else: forward jump on a `JUMP_FORWARD` past the else branch, or
  symmetric `JUMP_BACKWARD` in both branches
- Ternary expressions: branches each leave one value on the stack converging
  at the merge point
- Boolean short-circuit (`a or b`, `a and b`): the
  `COPY 1 ; TO_BOOL ; POP_JUMP_IF ; POP_TOP ; <alt>` pattern
- Inline list/set/dict comprehensions (3.13+): the
  `GET_ITER ; LOAD_FAST_AND_CLEAR ; SWAP ; BUILD_X 0 ; SWAP ; FOR_ITER ; ...`
  shape, with optional `if`-filter via `POP_JUMP_IF ; JUMP_BACKWARD ; ...`
  and post-comp save/restore via either `SWAP N ; STORE_FAST x (N-1 times)`
  or `STORE_FAST <accum> ; STORE_FAST <restore>`
- Generator expression / list comp via separate code objects (also still emitted
  by 3.14 for some patterns), reconstructed via `_build_comprehension`
- With statements: `COPY 1 ; LOAD_SPECIAL 1 ; SWAP 2 ; SWAP 3 ; LOAD_SPECIAL 0 ; CALL 0`
- Class-body annotations recovered from the `__annotate_func__` lambda's
  `LOAD_FROM_DICT_OR_GLOBALS <type> ... LOAD_CONST <name> ... STORE_SUBSCR` pattern

Error tolerance: every nested decoder catches IndexError / NotImplementedError /
AssertionError / AttributeError / TypeError and emits a `__decode_failed__(...)`
placeholder, then advances, so a single tricky opcode never aborts the whole
file. A final sweeper strips orphan trailers (naked `raise`, the
`if not None: raise` artefact, leftover `__decode_failed__` calls).

## AST cleanup

`work/cleanup.py` runs the following transforms on the decompiled AST:

- `TableSubstitutor` — `_ft[N]` becomes `Name(<builtin>)`, `_c[N]` becomes
  `Constant(<int>)`
- `XorStringDecoder` — recognizes the
  `bytes(b ^ ((K + i*M + N) & MOD) for i,b in enumerate(bytes.fromhex(<hex>))).decode()`
  pattern by walking the GeneratorExp AST and emits the decoded string
  literal directly
- `DeadCodeRemover` — drops `if False`, `if None is not None`, the
  `if x is not None: if x != x: return x` NaN-identity sandwich, and
  bounds-check fakes like `if x < 0: return None` on known-non-negative
  variables (matches the obfuscator's `_make_context_dead_block` patterns)
- `CFFUnflatten` — linearizes the
  `<sv> = <init>; while True: if <sv> == X: body; <sv> = Y; elif ...`
  state machine back to straight-line code. Two passes (once before, once
  after dead-code removal).
- `TrampolineCleanup` — collapses `def _tmp(...): ...; _ft[k] = _tmp; del _tmp`
  triplets to `def func_<k>(...): ...` and registers the integer key against
  the readable name
- `UserFuncCallRewrite` — replaces remaining `_ft[<int_key>]` references in
  load context with the corresponding user-function name
- `BoolSimplifier` — `not (X is Y)` -> `X is not Y`, etc.
- `DataclassAnnFix` — when a class carries `@dataclass`, converts plain
  class-body `Assign(name=value)` into `AnnAssign(name: int = value)` so
  `dataclass()` finds the fields (only used when the bytecode lacked an
  `__annotate_func__` we could mine; for round 008 we do mine it, but the
  fallback is in place)

## Behavioural verification

All six recovered files produce identical output to the obfuscated originals:

- `recovered/trivial/factorial.py` matches 13-line factorial table
- `recovered/trivial/fizzbuzz.py` matches FizzBuzz 1-20
- `recovered/trivial/binary_search.py` matches the 5 search() lines
- `recovered/medium/text_stats.py` matches the stats block
- `recovered/medium/todo_cli.py` matches the task list + stats line
- `recovered/hard/csvkit/` (package: __init__.py + parser.py + formatter.py +
  __main__.py) matches the CSV round-trip + bordered table + filtered table +
  total rows output when run as `python -m csvkit` from its parent directory

## What did not survive automatic recovery

The csvkit `__main__.py` entry point uses the CFF state-machine with `while True:`
implicit (no explicit condition) which my while-loop detector did not match,
producing a tangle of `if state == X` branches in flat order. The class methods
in `parser.py` use the 3.14 `LOAD_GLOBAL all ; COPY 1 ; LOAD_COMMON_CONSTANT all ; IS_OP 0 ; POP_JUMP_IF_FALSE`
specialization-check pattern which my decompiler emitted as `if all is all:`
spurious branching. Both were rewritten by hand based on the bytecode shape
(the data structures, method signatures, type-coercion rules, table-formatter
border drawing, and sort key order are all still derived from the bytecode of
the original obfuscated file). The smaller files all came out cleanly from the
automatic pipeline and were then identifier-renamed for readability.

## Files

- `/home/machine/projects/byepy/rounds/008/work/extract.py` — Stage 1 + 2 static extractor
- `/home/machine/projects/byepy/rounds/008/work/decompiler.py` — Python 3.14 bytecode decompiler
- `/home/machine/projects/byepy/rounds/008/work/cleanup.py` — AST cleanup transforms
- `/home/machine/projects/byepy/rounds/008/work/recover.py` — full pipeline
- `/home/machine/projects/byepy/rounds/008/recovered/...` — final recovered source
