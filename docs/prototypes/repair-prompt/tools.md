# Repair agent: tools (draft v1)

> PROTOTYPE, to react to. Defined once with LangChain `@tool`, `strict=True`, always in this order (the tool list is part of the cached prefix). Descriptions are what the model sees; `{…}` fields come from the migration spec.

| Tool | Arguments | Description the model sees | Returns |
|---|---|---|---|
| `read_file` | `path` | Read a file in the workspace, with line numbers. | File text, or an error if the path is outside the workspace |
| `search_guide` | `query` | Search the {guide_title} by component or API name. Returns the best-matching sections. | Up to 3 sections: title, "codemod" marker, text |
| `apply_edit` | `path`, `old_text`, `new_text` | Replace exactly one occurrence of `old_text` with `new_text` in an allowed file. Fails if `old_text` is missing or appears more than once. | OK with the patch size so far, or the reason it was rejected (blocked file, escape hatch, size limit, no unique match) |
| `run_verify` | `note` (one line: what you changed and why) | End this attempt and check the result. | Failures left in this file, new failures in other files, attempts left |
| `hand_off` | `reason` (one line) | Give this file to a human. Use it when the right fix needs a change you can't make. | Confirmation; the file's repair ends |

Guardrails live inside `apply_edit` and `read_file`, not in the prompt alone: the prompt explains them, the tools enforce them.
