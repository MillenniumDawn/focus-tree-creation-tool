@echo off
:: ============================================================
::  HOI4 Content Maker — Build Script
::  Double-click this to compile HOI4ContentMaker.exe
:: ============================================================

title HOI4 Content Maker - Build

set PYTHON=C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..

echo.
echo  =====================================================
echo   HOI4 Content Maker ^|^| Build System v2.0
echo  =====================================================
echo.

:: ── Check Python ─────────────────────────────────────────────
echo  Checking Python...
%PYTHON% --version
if errorlevel 1 (
    echo  [ERROR] Python not found at: %PYTHON%
    pause
    exit /b 1
)

:: ── Check PyInstaller ─────────────────────────────────────────
echo  Checking PyInstaller...
%PYTHON% -c "import PyInstaller; print('PyInstaller OK')" 2>nul
if errorlevel 1 (
    echo  [INFO] Installing PyInstaller...
    %PYTHON% -m pip install pyinstaller
    if errorlevel 1 (
        echo  [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

:: ── Check Pillow ──────────────────────────────────────────────
%PYTHON% -c "from PIL import Image" >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Installing Pillow...
    %PYTHON% -m pip install Pillow
)

:: ── Generate icon ─────────────────────────────────────────────
if not exist "%SCRIPT_DIR%icon.ico" (
    echo  [INFO] Generating icon.ico...
    %PYTHON% "%SCRIPT_DIR%generate_icon.py"
)

:: ── Clean ─────────────────────────────────────────────────────
echo.
echo  [STEP 1/3] Cleaning previous build...
if exist "%SCRIPT_DIR%build_tmp" rmdir /s /q "%SCRIPT_DIR%build_tmp"
if exist "%ROOT_DIR%\HOI4ContentMaker.exe" del "%ROOT_DIR%\HOI4ContentMaker.exe"
echo  Done.

:: ── Compile ───────────────────────────────────────────────────
echo.
echo  [STEP 2/3] Compiling... (1-3 minutes)
echo.

%PYTHON% -m PyInstaller "%SCRIPT_DIR%hoi4_content_maker.spec" --clean --noconfirm --distpath "%ROOT_DIR%" --workpath "%SCRIPT_DIR%build_tmp"

if errorlevel 1 (
    echo.
    echo  =====================================================
    echo   [ERROR] Build FAILED - see output above
    echo  =====================================================
    pause
    exit /b 1
)

:: ── Cleanup ───────────────────────────────────────────────────
echo.
echo  [STEP 3/3] Cleaning up...
if exist "%SCRIPT_DIR%build_tmp" rmdir /s /q "%SCRIPT_DIR%build_tmp"

echo.
echo  =====================================================
echo   Build SUCCESSFUL
echo   Output: HOI4ContentMaker.exe
echo  =====================================================
echo.
echo  Find HOI4ContentMaker.exe in the HOI4ContentMaker folder.
echo  No Python needed to run it - share it with anyone!
echo.
pause
