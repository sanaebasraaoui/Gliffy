#!/bin/bash
if command -v python3 &>/dev/null; then
    python3 cli.py migrate "$@"
else
    python cli.py migrate "$@"
fi

