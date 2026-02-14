## 2025-05-15 - Unrestricted File Read in Tool Runner

**Vulnerability:** The `read_file` tool allowed reading any file within the repository, including `.env` files containing secrets and credentials. While path traversal was guarded to `REPO_ROOT`, there were no restrictions on sensitive files within that root.
**Learning:** Agentic systems that provide file system access must have explicit blocklists for sensitive patterns (like `.env*`, `.git/`, `credentials.json`). "Inside the repo" is not a sufficient security boundary when the repo itself contains secrets.
**Prevention:** Implement a middleware or check in file access tools that validates against a list of sensitive file patterns and directories before allowing read access.
