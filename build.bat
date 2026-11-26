@echo off
REM ExTetris build (Windows): tests -> validate -> quick balance check -> packages in dist\
cd /d "%~dp0"
if "%PYTHON%"=="" set PYTHON=python
if "%GAMES%"=="" set GAMES=20
%PYTHON% -m pip install --quiet numpy pytest || goto :fail
%PYTHON% -m pytest v1_core_system v2_platform_release -q || goto :fail
for %%v in (variants\*.toml) do (
  %PYTHON% v2_platform_release\cli.py validate "%%v" || goto :fail
  %PYTHON% v2_platform_release\cli.py simulate "%%v" --games %GAMES% || goto :fail
  %PYTHON% v2_platform_release\cli.py package "%%v" --pyinstaller || goto :fail
)
echo Build complete: see dist\
exit /b 0
:fail
echo BUILD FAILED
exit /b 1
