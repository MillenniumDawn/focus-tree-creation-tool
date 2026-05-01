@echo off
:: ============================================================
::  HOI4 Content Maker — Build Script
::  Double-click this file to compile the .exe
::
::  Requirements (install once):
::    C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install pyinstaller
::    pip install Pillow          (optional, for icon generation)
::    pip install pyinstaller[encryption]  (optional, for bytecode encryption)
::
::  Output: dist\HOI4ContentMaker.exe
:: ============================================================

title HOI4 Content Maker - Build

echo.
echo  =====================================================
echo   HOI4 Content Maker ^|^| Build System v2.0
echo  =====================================================
echo.

:: ── Check Python is available ────────────────────────────────
C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found in PATH.
    echo  Install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

:: ── Check PyInstaller is installed ───────────────────────────
C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo  [INFO] PyInstaller not found. Installing...
    C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install pyinstaller
    if errorlevel 1 (
        echo  [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

:: ── Check Pillow (for icon generation) ───────────────────────
C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe -c "from PIL import Image" >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Pillow not found. Installing for icon generation...
    C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pip install Pillow
)

:: ── Generate icon.ico if it doesn't exist ────────────────────
if not exist icon.ico (
    echo  [INFO] Generating icon.ico...
    C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe generate_icon.py
    if errorlevel 1 (
        echo  [WARN] Icon generation failed. Building without custom icon.
        :: Patch spec to remove icon reference
        C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe -c "
import re, sys
with open('hoi4_content_maker.spec','r') as f: s=f.read()
s = s.replace(\"icon='icon.ico',\", \"icon=None,\")
s = s.replace(\"version='version_info.txt',\", \"\")
with open('hoi4_content_maker.spec','w') as f: f.write(s)
print('Spec patched - continuing without icon')
"
    )
)

:: ── Clean previous build ─────────────────────────────────────
echo.
echo  [STEP 1/3] Cleaning previous build...
if exist build   rmdir /s /q build
echo  Done.

:: ── Run PyInstaller ──────────────────────────────────────────
echo.
echo  [STEP 2/3] Compiling...
echo  (This may take 1-3 minutes on first run)
echo.

C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe -m PyInstaller hoi4_content_maker.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo  =====================================================
    echo   [ERROR] Build FAILED. See output above.
    echo  =====================================================
    pause
    exit /b 1
)

:: ── Post-build ───────────────────────────────────────────────
echo.
echo  [STEP 3/3] Finalising...

:: Copy the .exe to root folder for convenience
echo  Output written to parent folder.

:: Clean up PyInstaller temp folders (keep dist/)
if exist build_tmp rmdir /s /q build_tmp
if exist "hoi4_content_maker.spec.bak" del "hoi4_content_maker.spec.bak"

:: Report file size
for %%A in ("HOI4ContentMaker.exe") do (
    set size=%%~zA
)
C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe -c "s=%size%; print(f'  File size: {s/1024/1024:.1f} MB')" 2>nul

echo.
echo  =====================================================
echo   Build SUCCESSFUL
echo   Output: HOI4ContentMaker.exe
echo  =====================================================
echo.
echo  You can now distribute HOI4ContentMaker.exe
echo  No Python installation needed on the target machine.
echo.
pause
