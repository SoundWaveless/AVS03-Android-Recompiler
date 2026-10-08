@echo off
setlocal
cd /d "%~dp0"
set "DOCS_DIR=%~dp0..\..\docs"
set "LICENSE_FILE=%~dp0..\..\LICENSE"
if not exist "%DOCS_DIR%\README.md" set "DOCS_DIR=%~dp0docs"
if not exist "%LICENSE_FILE%" set "LICENSE_FILE=%~dp0LICENSE"
if not exist "%LICENSE_FILE%" set "LICENSE_FILE=%DOCS_DIR%\LICENSE"
py -m pip install --upgrade pyinstaller
if errorlevel 1 goto failed
py -m PyInstaller --noconfirm --clean --onefile --windowed --add-data "%~dp0android_patch;android_patch" --add-data "%DOCS_DIR%;docs" --add-data "%LICENSE_FILE%;docs" --name AVS03-Android-Builder avs03_wrapper_builder.py
if errorlevel 1 goto failed
echo.
echo Built dist\AVS03-Android-Builder.exe
pause
exit /b 0
:failed
echo Build failed. Check that Python and pip are installed.
pause
exit /b 1
