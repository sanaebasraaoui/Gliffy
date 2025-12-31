@echo off
python cli.py migrate %*
if %errorlevel% neq 0 (
    py cli.py migrate %*
)

