
import asyncio
import sys
import json
from pathlib import Path

# Add repo root and tools/telegram to sys.path
repo_root = Path(".").resolve()
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "tools/telegram"))

try:
    import tool_runner
except ImportError:
    from tools.telegram import tool_runner

async def main():
    print("Verifying execute()...")
    result = await tool_runner.execute("list_files", {"path": "."})
    print(f"Result length: {len(result)}")
    try:
        data = json.loads(result)
        if data.get("success"):
            print("PASS: execute('list_files') returned success.")
        else:
            print(f"FAIL: execute('list_files') returned error: {data.get('error')}")
    except json.JSONDecodeError:
        print("FAIL: Result is not valid JSON.")

if __name__ == "__main__":
    asyncio.run(main())
