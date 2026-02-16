#!/usr/bin/env python3
"""Tests for wa_opinions_to_obsidian.py"""

import unittest
import sys
import os
from pathlib import Path

# Add the directory containing the module to sys.path
sys.path.append(str(Path(__file__).parent))

from wa_opinions_to_obsidian import _iso_date_from_cell

class TestIsoDateFromCell(unittest.TestCase):
    def test_standard_formats(self):
        """Test standard date formats."""
        self.assertEqual(_iso_date_from_cell("Jan. 21, 2026"), "2026-01-21")
        self.assertEqual(_iso_date_from_cell("Jan 21, 2026"), "2026-01-21")
        self.assertEqual(_iso_date_from_cell("January 21, 2026"), "2026-01-21")
        self.assertEqual(_iso_date_from_cell("Feb. 1, 2024"), "2024-02-01")

    def test_sept_handling(self):
        """Test specific handling for 'Sept.' abbreviation."""
        self.assertEqual(_iso_date_from_cell("Sept. 21, 2026"), "2026-09-21")
        # "Sept" without dot is not currently handled by the function, so it returns None.
        # If this support is needed, the function should be updated.
        self.assertIsNone(_iso_date_from_cell("Sept 21, 2026"))

    def test_whitespace_handling(self):
        """Test handling of extra whitespace."""
        self.assertEqual(_iso_date_from_cell("  Jan.   21,   2026  "), "2026-01-21")
        self.assertEqual(_iso_date_from_cell("\tJan. 21, 2026\n"), "2026-01-21")

    def test_invalid_inputs(self):
        """Test invalid inputs return None."""
        self.assertIsNone(_iso_date_from_cell("Invalid Date"))
        self.assertIsNone(_iso_date_from_cell("2026-01-21"))  # Already ISO format is not parsed by this function
        self.assertIsNone(_iso_date_from_cell(""))
        self.assertIsNone(_iso_date_from_cell("   "))

    def test_edge_cases(self):
        """Test other edge cases."""
        # Leap year
        self.assertEqual(_iso_date_from_cell("Feb. 29, 2024"), "2024-02-29")
        # End of year
        self.assertEqual(_iso_date_from_cell("Dec. 31, 2025"), "2025-12-31")

if __name__ == '__main__':
    unittest.main()
