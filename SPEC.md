name: paramsneak
purpose: Probe a JSON/form API for mass-assignment by re-sending a captured create request with extra privilege/state fields, then GET-ing the resource back and emitting a working PoC curl for each field that stuck.
actionable_payoff: Final block prints, per stuck field, a copy-paste PoC curl that *re-creates* the privilege escalation. The user pastes it into a report or hands it to the program owner. Not a printed table to read.
language: python
why_language: stdlib `urllib`+`json`+`re` cover the whole job; quick to iterate, easy regex-based ID extraction, no third-party dep.
features:
- Parses a real curl create request (Content-Type honors form vs JSON)
- Auto-extracts the new resource ID from the create response (configurable regex)
- Optional GET-back template with `{id}` placeholder for stuck-field confirmation
- Built-in field dictionary for common privilege/state escalations + `--fields` override
- Per-attempt log-tree output (▷ / └─ / ►) and a final `>>` PoC block
- `NO_COLOR` and non-tty respected
input_contract: a curl that creates a resource, plus optional --get-back curl template with {id}
output_contract: log-tree per field attempt, then a `>>` PoC block listing copy-paste curl per stuck field
output_style: log-tree-plus-poc-list — leading-glyph log lines (▷/└─) and a `>>`-prefixed PoC block. No tables, no `---`, no box-drawing borders. Visibly distinct from scopesift/email-atom (wide ASCII tables) and curl2nuclei (yaml+box).
safe_test_target: httpbin.org/anything (echoes the body back, every field "sticks", makes the demo unambiguous)
synonym_names:
- massassign
- extrakey
- privfield
source_inspiration_url: https://owasp.org/www-community/attacks/Mass_Assignment_Cheat_Sheet
