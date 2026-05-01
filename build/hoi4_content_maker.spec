# -*- mode: python ; coding: utf-8 -*-
# ============================================================
#  HOI4 Content Maker — PyInstaller build spec
#  Run:  pyinstaller hoi4_content_maker.spec
# ============================================================

import sys
from PyInstaller.building.build_main import Analysis, PYZ, EXE

block_cipher = None   # set a string key here if you want bytecode encryption
                      # e.g. block_cipher = 'YOUR_SECRET_KEY_HERE'
                      # Requires: pip install pyinstaller[encryption]

a = Analysis(
    ['..\\hoi4_content_maker.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.font',
        'tkinter.scrolledtext',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'json',
        'os',
        're',
        'threading',
        'sys',
        'subprocess',
        'tempfile',
        'uuid',
        'copy',
        'hashlib',
        'ast',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PyQt5',
        'PyQt6',
        'wx',
        'gi',
        'unittest',
        'email',
        'html',
        'http',
        'xmlrpc',
        'lib2to3',
        'pydoc',
        'doctest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HOI4ContentMaker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,           # strip debug symbols
    upx=True,             # compress with UPX if available (reduces size ~30-40%)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # ← NO CMD window
    disable_windowed_traceback=True,   # don't show Python tracebacks in popups
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',                   # see build.bat — we generate this if missing
    version='version_info.txt',        # Windows file properties
)
