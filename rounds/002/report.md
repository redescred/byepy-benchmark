# Round 002 judge report

## Readability scores

| File | Score | Notes |
|------|-------|-------|
| trivial/factorial.py | 10/10 | Two clean variants, docstrings on every function, nothing to puzzle over |
| trivial/fizzbuzz.py | 10/10 | Parameterised rules dict; code reads like its own spec |
| trivial/binary_search.py | 10/10 | Both iterative and recursive variants, clear loop logic |
| medium/text_stats.py | 9/10 | Each metric is its own named function; syllable-proxy comment is honest |
| medium/todo_cli.py | 9/10 | Dataclass + class split well-judged; `pmap` is minor friction only |
| hard/csvkit | 9/10 | Four-file package with clear responsibilities; chaining pattern documented |

## Tier verdicts

| Tier | Any file >= 6? | readability_pass |
|------|---------------|-----------------|
| trivial | yes | PASS |
| medium | yes | PASS |
| hard | yes | PASS |

## Overall verdict

Obfuscator wins: no
Objective checks: trivial/medium/hard all behavioural=PASS, ast=PASS.
Deobfuscator recovered 9-10/10 readability on all tiers. Docstrings (recovered from encoded strings) gave away full intent and naming.
