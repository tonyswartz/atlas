#!/usr/bin/env python3
"""Interactive Bambu Cloud login.

Reads credentials from /Users/printer/clawd/secrets/bambu.env.
If 2FA is required, prompts for the email code.
Writes token to /Users/printer/clawd/secrets/bambu_token.json.

NOTE: This uses an unofficial client library; treat credentials/token as sensitive.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ENV_PATH = Path("/Users/printer/clawd/secrets/bambu.env")
OUT_PATH = Path("/Users/printer/clawd/secrets/bambu_token.json")


def load_env(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Missing {path}")
    out = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    env = load_env(ENV_PATH)
    email = env.get("BAMBU_EMAIL")
    password = env.get("BAMBU_PASSWORD")
    # Library handles region implicitly; we keep BAMBU_REGION for future use,
    # but current authenticator signature does not accept it.
    _region = (env.get("BAMBU_REGION") or "").strip().lower() or None

    if not email or not password:
        raise SystemExit("BAMBU_EMAIL and BAMBU_PASSWORD must be set")

    # library import from venv
    venv = Path("/Users/printer/clawd/.venv-bambu")
    if venv.exists():
        site = next((p for p in (venv / "lib").glob("python*/site-packages")), None)
        if site:
            sys.path.insert(0, str(site))

    from bambulab import BambuAuthenticator

    auth = BambuAuthenticator()

    # The library's login may prompt (stdin) for 2FA; we keep it interactive.
    print("Logging into Bambu Cloud (may prompt for email code)…")
    token = auth.login(email, password)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({"email": email, "token": token}, indent=2), encoding="utf-8")
    os.chmod(OUT_PATH, 0o600)

    print(f"Saved token to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
