# Coding Standards & Workflow

## Development Process
* **Planning:** Describe your approach and obtain approval before writing code.
* **Branching:** Create a branch `claude/{feature-name}` for any non-trivial changes.
* **Divide & Conquer:** Break complex problems into smaller, manageable tasks.

## Testing & Quality
* **Test-Driven Fixes:** For bugs, write a reproduction test first, then fix until it passes.
* **Coverage:** Suggest tests for happy paths, edge cases, and failure cases.
* **Post-Action:** After changes, summarize what changed, why, and suggest follow-up actions.

## Localization (Python Graphs)
* Translate Korean text to English for graph outputs to avoid font rendering issues.
* Provide the original Korean legend separately alongside the graph.
