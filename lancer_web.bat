@echo off
echo ==========================================
echo Démarrage de l'interface web Gliffy
echo ==========================================
echo Tentative de lancement avec 'python'...
python cli.py web
if %errorlevel% neq 0 (
    echo.
    echo Échec avec 'python', tentative avec 'py'...
    py cli.py web
)
pause

