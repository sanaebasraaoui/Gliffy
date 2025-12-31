@echo off
python cli.py scan %*
if %errorlevel% neq 0 (
    py cli.py scan %*
)

