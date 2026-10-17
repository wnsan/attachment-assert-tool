@echo off
rem Usage: compare.bat <template folder> <file> [more files] [--out report_dir] [--shift 2] ...
cd /d "%~dp0"
py -3 -m attachment_assert compare %*
exit /b %ERRORLEVEL%
