# v3-spec: plan

Documents only. Three tickets, one after another: each later one reads what the earlier wrote.
No design.md: the brief fixes the shape (areas, roadmap) and leaves only wording to the builder.

| Ticket | Serves | Depends on | Risk |
|---|---|---|---|
| [T-01](tickets/T-01.md) spec index, threat model, verdicts area | S-1, S-2, S-4a, S-6 (own reasons) | none | high |
| [T-02](tickets/T-02.md) the other areas with `anon-read`'s Not yet built scenarios, coverage table | S-3, S-4, S-6 (own reasons) | T-01 | medium |
| [T-03](tickets/T-03.md) roadmap check script, overlap check script and its saved output | S-5, S-6 | T-02 | low |

T-01 is high because it holds both critical areas of the brief (the threat model and safety
boundary, the verdict model); it is verified on its own before it lands.
