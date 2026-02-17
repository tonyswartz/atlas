
import sys
import os
import unittest
from unittest.mock import MagicMock
from pathlib import Path

# Add repo root to sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

# Mock telegram dependencies before importing bot
sys.modules["telegram"] = MagicMock()
sys.modules["telegram.ext"] = MagicMock()
sys.modules["telegram.constants"] = MagicMock()
sys.modules["dotenv"] = MagicMock()
sys.modules["yaml"] = MagicMock()
sys.modules["openai"] = MagicMock() # bot.py imports conversation which imports openai

# Now import bot (it will use the mocked modules)
from tools.telegram.bot import _escape_markdown

class TestMarkdownEscape(unittest.TestCase):
    def test_plain_text(self):
        self.assertEqual(_escape_markdown("Hello world"), "Hello world")

    def test_bold_normalization(self):
        # **bold** -> *bold*
        self.assertEqual(_escape_markdown("**Bold** text"), "*Bold* text")

    def test_link_preservation(self):
        # [Link](url) should NOT be escaped
        original = "Check [Google](https://google.com)"
        escaped = _escape_markdown(original)
        # Current implementation escapes [, so it fails this test.
        # We expect [Google](...) to remain as is
        self.assertEqual(escaped, "Check [Google](https://google.com)")

    def test_bracket_escaping(self):
        # [bracket] should be escaped
        self.assertEqual(_escape_markdown("Log [2024]"), "Log \\[2024]")

    def test_mixed_content(self):
        # Mixed links and brackets
        text = "Check [Google](https://google.com) and date [2024]"
        expected = "Check [Google](https://google.com) and date \\[2024]"
        self.assertEqual(_escape_markdown(text), expected)

if __name__ == "__main__":
    unittest.main()
