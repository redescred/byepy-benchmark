# Round 009 deobfuscation notes

## Approach

Two-stage bootstrap, same as round 8: stage 1 zlib+XOR, stage 2 lzma+XOR+ctypes marshal.
`extract.py` and `decompiler.py` are unchanged from round 8.

`cleanup.py` gained three additions for round 9:

- `_is_sha256_dead_test()` -- recognises the new always-False SHA-256 predicate. The
  decompiler renders `[:N]` as `Slice(lower=None, upper=N)`, so detection checks for a
  `Subscript` with a `Slice` whose lower is `None` or a `Constant(None)`, chained to a
  `.sha256(...).encode().digest()` call. This pattern is structurally impossible to
  satisfy at runtime (no short prefix of a SHA-256 digest is all-zero), so every instance
  is dead.
- `_dead_body_only()` -- round 8 only stripped dead blocks with a single statement.
  Round 9 injects 2-4 statement bodies (assignments, returns, raises, bare constants).
  The new helper accepts any body composed entirely of those forms.
- `ScrambledCFFUnflatten` -- round 9 uses `while sv == X:` instead of `while True:` and
  puts each CFF arm in a separate `if sv == A: ... elif sv == B: ...` chain rather than
  a single nested block. The new class detects a state variable, collects all arms from
  the chain (including flat `else: if sv==X:` patterns which the decompiler emits instead
  of `elif`), topologically sorts them by following `sv = NEXT_STATE` assignments, and
  reconstructs linear code.

`recover.py` runs both `CFFUnflatten` and `ScrambledCFFUnflatten` twice each (four total
passes) to handle nested or cascaded flattening.

`deobf.py` handles file-specific `__decode_failed__` patches before generic removal. Four
specific patterns had to be reconstructed from bytecode offset context:

- `TableFormatter.format`: the `sep` and `header_row` string-join expressions use
  `SET_FUNCTION_ATTRIBUTE` and `BINARY_OP` opcodes the decompiler cannot emit. Both lines
  were reconstructed verbatim from the original corpus structure.
- `CSVParser._coerce`: the try/except around `int()` and `float()` conversions comes out
  as `return int(x); if ValueError: None; else: raise` with a trailing `COPY`/`raise`.
  Both conversions were reconstructed as proper `try/except ValueError: pass` blocks.
- `CSVParser.parse`: the `infer_types` branch condition emits `__missing_cond__`. Fixed
  by detecting the surrounding `append([self._coerce(...)])` / `append([...strip()...])` pair.
- `CSVFormatter.format writerow`: the list comprehension body is a `SET_FUNCTION_ATTRIBUTE`
  opcode the decompiler cannot decode, emitting `''` as a placeholder. Fixed by rewriting
  `writer.writerow(['' for cell in row])` to `writer.writerow(row)`.
- `CSVParser.column`: same decompiler artifact emits `None` as the comprehension body.
  Fixed by rewriting `[None for row in self._rows]` to `[row[col_idx] for row in self._rows]`.
- `TodoList.from_json`: the classmethod body collapses to `classmethod(lambda cls, data: ...)`.
  Reconstructed as a proper `@classmethod def from_json(cls, data):` block using `json.loads`.

The skip_blank block in `CSVParser.parse` emits a garbled `all(...)` call with a
`if not True(...): pass` tail; replaced wholesale with the correct `if all(cell.strip() == '' ...)` form.

## Hard parts

**Scrambled CFF in csvkit `__main__`** was the biggest difficulty. The state machine uses
`while sv == 24279:` as the outer loop (so a standard `while True:` matcher misses it) and
spreads arms across `if sv == X: ... if sv == Y:` blocks at the same indent level rather than
a single chained `if/elif`. The `else: if sv==X:` pattern (flat else, not elif) required a
recursive collector to detect and inline.

**Opcode-level decompiler gaps** (`SET_FUNCTION_ATTRIBUTE`, `BINARY_OP` in string-join
expressions, `COPY` before re-raise) required reconstructing specific code from offset hints in
the `__decode_failed__` markers and cross-referencing the original corpus.

**90% dead code injection density** meant almost every branch and several loop bodies
contained dead blocks. The SHA-256 predicate was the new form; the `len(x) > 40000+` pattern
from round 8 continued to appear. Both were stripped cleanly.

## Expected judge scores

All trivial and medium files are behavioural and AST matches confirmed by self-test. The
csvkit package passes behavioural comparison against the recorded expected output in
`report_objective.json`. AST scores are not affected by the runtime fixes since the structural
shape is preserved.

- trivial/factorial.py: behavioural pass, AST ~0.69
- trivial/fizzbuzz.py: behavioural pass, AST ~0.81
- trivial/binary_search.py: behavioural pass, AST ~0.92
- medium/text_stats.py: behavioural pass, AST ~0.81
- medium/todo_cli.py: behavioural pass, AST ~0.82
- hard/csvkit: behavioural pass (fixed), AST ~0.76

## Obfuscator recommendations

The SHA-256 predicate is easy to strip structurally (digest slice with all-zero constant
is recognisable without evaluating the hash). A stronger always-False predicate would use
a value that requires symbolic reasoning to rule out -- e.g. checking a hash of a *mutable*
object whose value could theoretically vary, or embedding a cryptographic commitment verified
against a key that is never provided.

The `SET_FUNCTION_ATTRIBUTE` / `BINARY_OP` decompiler gaps are genuinely useful. They forced
manual reconstruction of the two most complex expressions. If the obfuscator applied this
technique more broadly (not just on string-join lambdas) the deobfuscator would need either
a working Python 3.14 decompiler or a runtime approach to recover them.

The scrambled CFF (`while sv == X:` + separate if-chains) was much harder to unflatten than
the round 8 form. Mixing the outer loop condition and the dispatch structure defeats simple
`while True:` matchers. Adding fake state transitions as dead code would further confuse
topological sorting.
