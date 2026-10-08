@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller
if errorlevel 1 goto failed
py -m PyInstaller --noconfirm --clean --onefile --windowed --add-data "%~dp0android_patch;android_patch" --add-data "%~dp0DISCLAIMER-ACKNOWLEDGMENT.md;." --add-data "%~dp0README.md;." --add-data "%~dp0LICENSE;." --name AVS03-Android-Builder avs03_wrapper_builder.py
if errorlevel 1 goto failed
echo.
echo Built dist\AVS03-Android-Builder.exe
pause
exit /b 0
:failed
echo Build failed. Check that Python and pip are installed.
pause
exit /b 1
