@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (py build.py & goto :done)
where python >nul 2>nul && (python build.py & goto :done)
echo Nerastas Python. Atsisiuskite is https://www.python.org/downloads/ (pazymekite "Add python.exe to PATH").
:done
echo.
pause
