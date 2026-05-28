# Round 006 deobfuscation notes

## Approach

Two-stage static extraction. The runtime check (`sys.gettrace`, `getprofile`, and the
`type(zlib.decompress).__name__` guard) blocks dynamic execution, but the bootstrap
is straightforward to do by hand:

1. `ast.parse` the obfuscated file, pull `_D` and `_K` from the module-level
   assignments, and run `zlib.decompress(b ^ K[i%16])` to recover Stage 1 source.
2. Parse Stage 1, pull `_D2` and `_K2`, run `lzma.decompress(b ^ K2[i%16])` to get
   the marshal payload.
3. Call `marshal.loads(payload)` directly (not via the bootstrap, so no tracing
   check) to get the top-level code object.
4. Recursively `dis.dis` each code object and its `co_consts` to read the
   bytecode.

The helpers I built live under `/home/machine/projects/byepy/rounds/006/work/`:

- `extract.py`: stage 1 + stage 2 byte recovery, returns the top-level code object.
- `disasm.py`: recursive `dis.dis` dump.
- `decode_strings.py`: walks the consts, spots the `MAKE_FUNCTION` -> base64 +
  XOR-generator pattern, and prints the decoded string for each pair.
- `decode_ft.py`: rebuilds the `_ft` builtin dispatch dict from the module
  bytecode by pairing each integer key with the corresponding XOR-encoded name
  tuple.

## Round 6 specifics

The new wrinkle this round was the `_ft` dispatch dict. Every builtin reference
(`print`, `len`, `range`, etc.) is replaced with `_ft[N]`, where the dict is
built once at module top with entries like

    _ft = {19491: getattr(__import__('builtins'), bytes(g(tup)).decode()), ...}

and each `g` is a single-byte XOR generator with the byte stored as a
`LOAD_SMALL_INT` inside the lambda. `decode_ft.py` walks the module bytecode,
matches each `MAKE_FUNCTION` with the next `LOAD_CONST` tuple, decodes the name,
and recovers the integer-to-builtin map. From there, every `_ft[12345]` in the
disassembly is replaced mentally with the real builtin.

String constants follow the same pattern (base64 + per-string XOR byte). The
XOR byte for each string is the one in its accompanying generator lambda; the
master constant table contains base64 blobs only.

Code obfuscation features I had to undo:

- All function names set to `<lambda>` (only `<module>` is unchanged).
- `co_varnames`, `co_freevars`, `co_cellvars` scrambled to `l/I/I/l` garbage.
- Annotation lambdas (PEP 649) are present alongside every real function;
  they always raise on `format > 2` and otherwise return a dict mapping the
  obfuscated arg/return name to a builtin type.
- Liberal dead-code junk: `_k = list(range(8)); _k.sort(reverse=True); del _k`
  appears before nearly every action; `if hash(0)+hash(1)==hash(2): pass`,
  `if type(None) is int: ...`, and `if abs(-1) < 0: ...` are all unreachable
  predicate guards.
- Some functions use a state-machine layout: a state variable is assigned an
  arbitrary marker integer, then a chain of `if state == N` blocks dispatches
  to the real body, with each block setting the next state. The state values
  themselves carry no meaning, so unraveling the order recovers a normal
  straight-line function.

## What was recovered

### trivial/

- `factorial.py`: recursive and iterative factorial, `if __name__ == '__main__'`
  prints 0! .. 12!.
- `fizzbuzz.py`: `fizzbuzz_value(n, mapping=None)` with `{3:'Fizz', 5:'Buzz'}`
  default, plus `fizzbuzz_lines(n)` and a CLI driver.
- `binary_search.py`: iterative and recursive variants, demo driver over
  `list(range(0, 100, 3))`.

### medium/

- `text_stats.py`: `tokenize`, `sentences`, `word_counter`, `top_n`,
  `avg_word_length`, `avg_sentence_length`, `flesch_score` (Flesch reading-ease
  with `ASW = avg_word_length/3` as the syllable proxy), `hapax_words`,
  `type_token_ratio`, `compute_stats`, `print_stats`. CLI reads `sys.argv[1]`
  or falls back to a built-in fox/dog sample paragraph.
- `todo_cli.py`: `Task` dataclass (id, title, done, priority, tags) with
  `mark_done` / `mark_undone` / `__str__`, and `TodoList` class with add /
  get / remove / complete / uncomplete / filter_by_tag / filter_by_priority /
  pending / completed / all_sorted / stats / to_json / from_json. Demo `main`
  populates five tasks, completes two, prints all/pending/work views, then a
  stats line.

### hard/csvkit/

The original package was consolidated into the single bootstrap
`__main__.py`. The recovered split:

- `__init__.py`: re-exports plus `__all__`, `__version__ = '0.1.0'`.
- `formatter.py`: `CSVFormatter(delimiter, quoting)` with `format(headers, rows)`
  and `format_dicts(records)`; `TableFormatter(padding, border)` with
  `_col_widths`, `_pad`, `format`, `format_dicts`.
- `parser.py`: `CSVError(Exception)` plus `CSVParser` with `BOOL_TRUE` /
  `BOOL_FALSE` class sets, `_coerce` (None / bool / int / float / str cascade),
  `parse`, `rows`, `dicts`, `column`, `filter_rows`, `sort_by`, `__len__`,
  `__iter__`.
- `__main__.py`: `SAMPLE` (name,age,city,active CSV), `main()` that parses,
  CSV-round-trips, prints a TableFormatter table, then filters to
  `city == 'London'`, sorts by `age`, and prints the row total.

All recovered files run cleanly and produce the expected output:

- factorials 0! through 12!
- FizzBuzz 1..20
- binary_search returns indexes 0/5/14/33 and -1 for the missing 7
- text_stats produces 60 words / 33 unique / 10 sentences / Flesch 93.11 / etc.
- todo_cli prints the all/pending/work sections with 2/5 done
- csvkit prints the round-tripped CSV, the bordered table, the London
  filter sorted by age, and `Total rows: 4`.
