@echo off
:: ============================================================
::  HOI4 Content Maker — ENCRYPTED Build
::
::  Bytecode inside the .exe is AES-128 encrypted.
::  Someone who extracts the bundle gets encrypted .pyc files,
::  not readable Python source.
::
::  Output: ..\HOI4ContentMaker.exe
:: ============================================================

title HOI4 Content Maker - Encrypted Build

set PYTHON=C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe

echo.
echo  =====================================================
echo   HOI4 Content Maker ^|^| ENCRYPTED Build
echo  =====================================================
echo.

:: ── Check Python ─────────────────────────────────────────────
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found at: %PYTHON%
    pause
    exit /b 1
)

:: ── Install encryption support ───────────────────────────────
echo  [INFO] Installing encryption support...
%PYTHON% -m pip install "pyinstaller[encryption]" --quiet
%PYTHON% -m pip install tinyaes --quiet

:: ── Patch spec to enable encryption ─────────────────────────
echo  [INFO] Enabling bytecode encryption in spec...
%PYTHON% patch_spec_encrypted.py

if errorlevel 1 (
    echo  [ERROR] Failed to patch spec for encryption.
    pause
    exit /b 1
)

:: ── Generate icon if needed ───────────────────────────────────
if not exist icon.ico (
    echo  [INFO] Generating icon.ico...
    %PYTHON% generate_icon.py
)

:: ── Clean previous build ─────────────────────────────────────
echo  [STEP 1/3] Cleaning previous build...
if exist build_tmp rmdir /s /q build_tmp

:: ── Build ────────────────────────────────────────────────────
echo.
echo  [STEP 2/3] Compiling with encryption...
echo  (First run may take 3-5 minutes)
echo.

%PYTHON% -m PyInstaller hoi4_content_maker_enc.spec --clean --noconfirm --distpath "..\" --workpath ".\build_tmp"

if errorlevel 1 (
    echo.
    echo  =====================================================
    echo   [ERROR] Encrypted build FAILED.
    echo   Try the standard build.bat instead.
    echo  =====================================================
    if exist hoi4_content_maker_enc.spec del hoi4_content_maker_enc.spec
    pause
    exit /b 1
)

:: ── Finalise ─────────────────────────────────────────────────
echo.
echo  [STEP 3/3] Finalising...
if exist build_tmp rmdir /s /q build_tmp
if exist hoi4_content_maker_enc.spec del hoi4_content_maker_enc.spec

echo.
echo  =====================================================
echo   Encrypted build SUCCESSFUL
echo   Output: ..\HOI4ContentMaker.exe
echo   Bytecode is AES-128 encrypted inside the bundle.
echo  =====================================================
echo.
pause
