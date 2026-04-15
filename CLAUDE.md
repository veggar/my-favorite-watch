# General Thinking Rules

* Before writing any code, describe your approach and wait for approval.
* If the requirements are ambiguous, ask clarifying questions before writing any code.
* If there is any inconsistency among the requirements, propose one consistent interpretation and obtain confirmation.
* Break complex problems into two or more smaller tasks. Use a divide-and-conquer approach.
* Every time I correct your mistake, add a new rule to these instructions to help prevent the same mistake from happening again.
* Do not silently assume missing requirements for business logic, security, or data handling. State assumptions explicitly.

## Language Rules

* All answers, questions, and explanatory text, excluding code, must be written in Korean.

## Security & Permissions

* If an installation requires admin privileges rather than general user privileges, explain why and obtain approval first.
* Sensitive data such as API keys, tokens, passwords, and private credentials must be provided through secure settings or environment variables, not hardcoded in code or prompts.
* Never expose secrets in logs, code snippets, screenshots, or commit history.

## Project Rules

* If a `PRD.md` file exists and the requirements change, update `PRD.md` accordingly.
* If `PRD.md` conflicts with newly given instructions, highlight the conflict and obtain confirmation before proceeding.
* For any non-trivial code change, create a branch first before proceeding.
* For major feature changes, create a new branch before making modifications, then request confirmation before merging.
* Use the branch naming convention: `claude/{feature-name}`.

## Architecture Rules

* Prefer Server-Side Rendering (SSR) unless there is a clear reason to use another rendering strategy.

## Coding Standards

* After writing code, list what could break and suggest tests to cover it.
* For each change, update all related code, configuration, tests, and documentation as needed to keep the project consistent.
* When there is a bug, start by writing a test that reproduces it, then fix the bug until the test passes.
* When generating graphs with Python, translate Korean text into English so that Korean characters do not appear in the graph output.
* When graph labels are translated into English, provide the original Korean legend separately alongside the graph output.
* When suggesting tests, include happy paths, edge cases, and failure cases.
* After making changes, summarize what changed, why it changed, and any follow-up actions needed.

## Commands

* Explicitly document the installation and execution steps for the project.
* If the documented installation or execution steps are missing, outdated, or inconsistent with the actual project setup, update these instructions before proceeding.
* When updating commands, ensure that required environment variables, ports, entry points, and prerequisite steps are clearly specified.
* Write the installation method in the "Install:" section below and the execution command in the "Run:" section.

  * Install: 
  * Run: 
