## 2025-05-15 - Structured Command Menus
**Learning:** In chat interfaces, long lists of commands are overwhelming. Grouping commands by category (e.g., "Capture Ideas", "Planning") and using emojis as visual anchors significantly improves scannability.
**Action:** Always structure /help output with clear sections and visual hierarchy, rather than a flat list.

## 2026-02-15 - Continuous Typing Indicators
**Learning:** LLM responses can be slow (e.g. tool usage), and single "typing" indicators in Telegram expire, causing user uncertainty about bot status.
**Action:** Use an async context manager to continuously refresh typing indicators for long-running operations.
