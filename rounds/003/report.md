# Round 003 judge report

## Readability scores

| Tier | File | Score | Notes |
|------|-------|-------|-------|
| trivial | factorial.py | 10/10 | Perfect recovery — iterative + recursive, typed, clear names |
| trivial | fizzbuzz.py | 10/10 | Generalised rules dict, generate helper, completely transparent |
| trivial | binary_search.py | 9/10 | Both variants clean; high==-1 sentinel is a minor pause |
| medium | text_stats.py | 9/10 | Well-decomposed single-responsibility functions |
| medium | todo_cli.py | 9/10 | Clean dataclass model; `pmap` is minor friction only |
| hard | csvkit/__init__.py | 10/10 | Minimal, correct |
| hard | csvkit/parser.py | 8/10 | Solid structure; filter_rows/sort_by return contract undocumented |
| hard | csvkit/formatter.py | 8/10 | Helpers clear; cell-building loop slightly dense but followable |
| hard | csvkit/__main__.py | 9/10 | Clear entry point, readable SAMPLE constant |

## Tier verdicts

| Tier | Any file >= 6? | readability_pass |
|------|---------------|-----------------|
| trivial | yes | PASS |
| medium | yes | PASS |
| hard | yes | PASS |

## Overall verdict

Obfuscator wins: no
Objective checks: trivial/medium/hard all behavioural=PASS, ast=PASS.
Deobfuscator recovered 8-10/10 readability on all tiers.

## How deobfuscation succeeded

Single files (trivial/medium): patched `marshal.loads` before executing bootstrap, captured the code object, ran `dis.dis()` on it, reconstructed source from bytecode disassembly. Python 3.14 bytecode was no obstacle — co_varnames retained the renamed but still short-ish l/I identifiers; LLM reconstruction from dis output was straightforward.

Package (hard/csvkit): AST-level only. Read XOR constants directly from source (literal in file), decoded strings, stripped dead code blocks (always-false guards were obvious), unrolled the CFF state machine (single linear while-True dispatch).
