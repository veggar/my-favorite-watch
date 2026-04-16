# Security & Permissions

## Secret Management
* **No Hardcoding:** API keys (Google, TMDb), tokens, and passwords must be handled via environment variables.
* **Sanitization:** Never expose secrets in logs, code snippets, or commit history.

## Permissions
* **Admin Access:** Explain the necessity and obtain approval before requesting admin/sudo privileges.
* **Explicit Assumptions:** Do not silently assume requirements for security or data handling; state them explicitly.
