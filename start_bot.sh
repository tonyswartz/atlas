#!/bin/bash
cd /Users/printer/atlas
/opt/homebrew/bin/python3 tools/telegram/bot.py >> logs/telegram_bot.log 2>&1 &
