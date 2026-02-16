## 2025-05-15 - Unrestricted File Read in Tool Runner

**Vulnerability:** The `read_file` tool allowed reading any file within the repository, including `.env` files containing secrets and credentials. While path traversal was guarded to `REPO_ROOT`, there were no restrictions on sensitive files within that root.
**Learning:** Agentic systems that provide file system access must have explicit blocklists for sensitive patterns (like `.env*`, `.git/`, `credentials.json`). "Inside the repo" is not a sufficient security boundary when the repo itself contains secrets.
**Prevention:** Implement a middleware or check in file access tools that validates against a list of sensitive file patterns and directories before allowing read access.

## 2025-05-15 - Unauthenticated Browser Server Control
**Vulnerability:** The `tools/browser/browser_server.py` server was running on `localhost:19527` without any authentication. This allowed any local process or user to control the browser (navigate, screenshot, upload files) by sending simple HTTP requests.
**Learning:** Tools running as local servers often lack default security because they are "local only," but they are vulnerable to local privilege escalation or confused deputy attacks if another process can reach them.
**Prevention:** Implement mandatory authentication for all local tool servers. Use a shared secret (like an environment variable token) and validate it on every request using secure comparison functions (`secrets.compare_digest`).
