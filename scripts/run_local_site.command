#!/bin/zsh

cd /Users/cocachloe/Documents/职业/retail-channel-ai-assistant || exit 1
echo "Starting retail channel dashboard..."
echo "Keep this Terminal window open while using http://127.0.0.1:8502/"
echo
exec ./scripts/launchd_streamlit.sh
