#!/usr/bin/env python3
"""
News Briefing Wrapper
Delegates to local_news.py for the actual news briefing.
This script exists for backward compatibility with any references to news_briefing.
"""

import sys
import os

# Ensure we can import from the scripts directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from local_news import fetch_news, generate_summary, load_state, log_to_obsidian

def main():
    """Run news briefing"""
    state = load_state()
    articles = fetch_news()
    summary = generate_summary(articles, state)
    print(summary)

if __name__ == "__main__":
    main()
