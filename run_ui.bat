@echo off
rem Start the browser UI; templates are stored in .\attachment_assert_workspace
cd /d "%~dp0"
py -3 -m attachment_assert ui --workspace "%~dp0attachment_assert_workspace" %*
pause
