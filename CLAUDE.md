# Gerneral Thinking Rules

- Before writing any code, describe your approach and wait for approval. Always ask clarifying questions before writing any code if requirements are ambiguous.
- If a task requires changes to more than 3 files, stop and break it into smaller tasks first.
- If there is a deviation from consistency among the requirements, propose a consistent item and obtain confirmation.
- If a task requires changes to more than 3 files, stop and break it into smaller tasks first.
- After writing code, list what could break and suggest tests to cover it.
- When there’s a bug, start by writing a test that reproduces it, then fix it until the test passes.
- For each change, the related codes must also be updated if necessary.
- Every time I correct your mistake, you add a new rule to the instructions to make sure it doesn't happen again.
- If an installation requires admin privileges rather than general privileges, you must provide an explanation and obtain approval.
- Data requiring security must be entered through settings.
  
## Outputs

- Answers and question, rules, excluding code, are in Korean.

## Project Rules

- If a PRD.md exists for the requirements, update the PRD.md when the requirements change.
- If there is a request for code modifications requiring major feature changes, create a branch, modify the code, and get confirmation for the merge.
- For changes, **create a branch first**, then proceed.
- branch name: claude/{feature name}
- Use Server Side Rendering.

## Coding Standards

- To prevent Korean characters from being included in the graphs output by the Python code, translate them into English and use them.
- The translated legend applied to the graph is provided in its original Korean text separately from the graph.

## Commands

- Run: `export $(cat .env | xargs) && python3 app.py`  (포트: 8080)
- Install: `pip install -r requirements.txt`
