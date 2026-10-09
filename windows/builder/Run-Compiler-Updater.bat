@echo off
cd /d "%~dp0"
py avs03_compiler_updater.py
if errorlevel 1 pause
