# Round 007 deobfuscation notes

## Overview

All seven obfuscated targets share the same two-stage bootstrap. Stage 1 is a
small Python source file that XOR-decrypts and zlib-inflates Stage 2. Stage 2
is a longer Python source file that XOR-decrypts and LZMA-inflates a marshal-
serialised code object. Stage 2 then evaluates that code object under a custom
globals dictionary whose only interesting entries are a name-mangled lookup
table mapping integer keys to builtin functions (`print`, `len`, `range`, etc.).

The marshalled code object is what actually implements the program.

## Bootstrap

### Stage 1: outer file
```
import zlib as _Z, sys as _s
if _s.gettrace() is not None or _s.getprofile() is not None: raise SystemExit(1)
if type(_Z.decompress).__name__ != 'builtin_function_or_method': raise SystemExit(1)
_D = b'<ciphertext>'
_K = b'<16-byte key>'
_src = _Z.decompress(bytes(_b^_K[_i%16] for _i,_b in enumerate(_D))).decode()
del _D, _K
getattr(__import__('builtins'),'exec')(_src)
```

Recovery: parse the AST, grab the constant bytes for `_D` and `_K`, XOR with
the 16-byte key (cycling), then zlib-decompress.

### Stage 2: produced source
Similar shape but uses `ctypes.pythonapi.PyMarshal_ReadObjectFromString` to
reconstitute a code object from the LZMA-decompressed marshal data, then
builds a small dict like

```
llc02eb41770b7ddbf = {}
llc02eb41770b7ddbf[83]    = getattr(builtins, decode('46404c292a2804041e', ...))   # 'enumerate'
llc02eb41770b7ddbf[12258] = getattr(builtins, ...)                                  # 'ValueError'
...
```

The string decoder is a fixed template (also used inside the marshalled code):
```
bytes(_b ^ ((C + _i*M + A) & 255) for _i, _b in enumerate(bytes.fromhex(HEX))).decode()
```
with three small integers C, M, A passed as `LOAD_SMALL_INT` opcodes in the
generator lambda. Recovery extracts those three constants from each lambda's
bytecode and applies the same formula to the hex string that follows.

## Inside the code object

The marshalled code is real Python 3.14 bytecode. It uses several layers of
nuisance:

- **Name mangling**: every user-defined name becomes `l<hex>` or `I<hex>` or
  random `lIlI...` strings.
- **Builtin indirection**: any builtin (`print`, `range`, `len`, etc.) is
  fetched through `globals_dict['llc02eb41770b7ddbf'][KEY]` where KEY is an
  arbitrary integer baked into the bytecode at compile time. The decoded
  globals lookup dict has only a dozen or so entries per file.
- **Inline string obfuscation**: every string literal that survives into the
  marshalled code is encoded with the same `bytes(...)`/XOR/`fromhex`/`decode`
  template above. Headings, error messages, format-spec strings, even sample
  text and CSS-style separators all live behind these expressions.
- **Dead-code traps**: most function bodies are sprinkled with `if x != x:
  return x` checks. `x != x` is only true for NaN, so the dead branches never
  fire; they exist purely to slow down a casual reader.
- **State-machine control flow** (csvkit demo only): the demo function for
  the hard target dispatches every basic block off a single local variable
  containing one of fifteen-or-so integer state IDs, transitioning through
  the demo's actual steps in shuffled order.

## Recovery approach

I never executed the bootstrap directly. Static extraction is enough:

1. Parse Stage 1 via `ast`, pull out `_D` and `_K`, XOR + zlib to get Stage 2.
2. Parse Stage 2 via `ast`, pull out `_D2`/`_K2`, XOR + lzma + `marshal.loads`
   to obtain the code object. Also enumerate the `llc02eb41770b7ddbf[k] = ...`
   assignments and resolve each to its builtin name.
3. Walk the code object recursively, find every `MAKE_FUNCTION` whose code
   begins with `RETURN_GENERATOR`, treat that as a string-decoder lambda,
   read its three `LOAD_SMALL_INT` constants, then pair it with the next
   `LOAD_CONST` (the hex string). That gives a complete `hex -> plaintext`
   table for the file.
4. `dis.dis` the code object plus all nested code objects, then read the
   bytecode by hand to reconstruct clean Python source. The string table and
   builtin lookup let me name everything sensibly: a `LOAD_CONST 22286`
   followed by `BINARY_OP 26` is just a call to `range`, etc.

The helper scripts live in `rounds/007/work/`:
- `deobf.py`: Stage 1 only
- `stage2.py`: Stages 1 + 2 (returns the code object and lookup)
- `strings.py`: Stages 1 + 2 + decode every inline string
- `analyze.py`: dumps everything (lookup, structure, strings, full disassembly)
- `run_safely.py`: builds the right globals dict and runs the code object,
  used to verify behaviour and to sanity-check edge cases (Flesch score
  formula, sort-key semantics, error message shape).

## Per-target notes

- **trivial/factorial.py**: two functions, recursive and iterative, plus a
  driver loop. Vanilla once decoded.
- **trivial/fizzbuzz.py**: `fizzbuzz_value(n, mapping=None)` with default
  `{3:'Fizz', 5:'Buzz'}`, plus a list-builder `fizzbuzz(n)` that drives 1..20.
- **trivial/binary_search.py**: iterative and recursive variants, driver
  loop searches a `range(0,100,3)` list for five targets.
- **medium/text_stats.py**: tokenize, sentence-split (regex), Counter,
  Flesch score with a quirky formula (`206.835 - 1.015 * avg_sentence_length
  - 84.6 * (avg_word_length / 3.0)`), type-token ratio, hapax legomena,
  top-N counts. Tokenizer is reused as a syllable-count proxy for sentences.
- **medium/todo_cli.py**: `@dataclass` `Task`, `TodoList` with add/get/remove/
  complete/uncomplete/filter_by_tag/filter_by_priority/pending/completed/
  all_sorted/stats/to_json/from_json, plus a demo that adds five tasks and
  prints three views and a stats line.
- **hard/csvkit/**: package with stub `__init__.py`, `formatter.py`,
  `parser.py` (all `# stub` in the original; everything lives in `__main__.py`).
  `__main__.py` defines `CSVFormatter`, `TableFormatter`, `CSVError`,
  `CSVParser` and a demo. The demo's control flow is a state machine over
  integer IDs; tracing the transitions gives the straight-line sequence
  parse -> print round-trip -> print table -> print London-filtered table -> print row count.
