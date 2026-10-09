## v3-bakeoff

89 scored observation answers over 11 photos. Labels: drafted by the coding agent and re-checked by it in a second pass; not independently reviewed by a person.

| model | accuracy | false yes | false no | too cautious | rejected | in-view questions | warm latency (prompt + generate) |
|---|---|---|---|---|---|---|---|
| gemma3:4b | 65% | 6 | 4 | 21 | 36 | 20% | 33.02 s (0.31 + 31.28) |
| gemma4:e2b | 85% | 1 | 6 | 6 | 22 | 40% | 1.6 s (0.12 + 1.45) |
| gemma4:e4b | 84% | 4 | 5 | 5 | 24 | 47% | 2.3 s (0.05 + 2.21) |
