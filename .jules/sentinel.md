## 2025-05-15 - Unrestricted File Read in Tool Runner

**Vulnerability:** The `read_file` tool allowed reading any file within the repository, including `.env` files containing secrets and credentials. While path traversal was guarded to `REPO_ROOT`, there were no restrictions on sensitive files within that root.
**Learning:** Agentic systems that provide file system access must have explicit blocklists for sensitive patterns (like `.env*`, `.git/`, `credentials.json`). "Inside the repo" is not a sufficient security boundary when the repo itself contains secrets.
**Prevention:** Implement a middleware or check in file access tools that validates against a list of sensitive file patterns and directories before allowing read access.

## 2026-02-15 - Information Disclosure via Exception Messages and Hardcoded Paths

**Vulnerability:** The Telegram bot was configured to reply with the raw exception message `f"Couldn't do that: {e}"` when an error occurred, exposing internal implementation details and potential stack traces to users. Additionally, a hardcoded absolute path `/Users/printer/...` revealed the system username and directory structure.
**Learning:** Error messages in user-facing interfaces (especially chat bots) must be sanitized. "Fail securely" means not leaking internal state during failure. Hardcoded paths are a dual risk: they break deployment portability and leak environment information.
**Prevention:** Use a global exception handler that logs the full traceback internally (for developers) but returns a generic, safe error message to the user. Use dynamic path resolution (e.g., relative to repo root) for all file operations.
