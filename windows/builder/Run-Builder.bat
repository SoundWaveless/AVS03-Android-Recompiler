@echo off
cd /d "%~dp0"
if exist avs03_compiler_updater.py (
  py avs03_compiler_updater.py
  if errorlevel 1 pause
  exit /b
)
py avs03_wrapper_builder.py
if errorlevel 1 pause
