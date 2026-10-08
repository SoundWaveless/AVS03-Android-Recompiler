@echo off
cd /d "%~dp0"
py avs03_wrapper_builder.py
if errorlevel 1 pause
