#!/bin/bash
if command -v python3 &>/dev/null; then
    python3 cli.py scan "$@"
else
    python cli.py scan "$@"
fi

