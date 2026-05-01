# -*- mode: python ; coding: utf-8 -*-
# HOI4 Content Maker — PyInstaller spec

block_cipher = None

a = Analysis(
    ['..\\hoi4_content_maker.py'],
    pathex=['..'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter', 'tkinter.ttk', 'tkinter.messagebox',
        'tkinter.filedialog', 'tkinter.font', 'tkinter.scrolledtext',
        'PIL', 'PIL.Image', 'PIL.ImageTk',
        'json', 'os', 're', 'threading', 'sys',
        'subprocess', 'tempfile', 'uuid', 'copy', 'hashlib', 'ast',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'pandas',
        'PyQt5', 'PyQt6', 'wx', 'unittest',
        'email', 'http', 'xmlrpc', 'lib2to3',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HOI4ContentMaker',
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=True,
    icon='icon.ico',
    version='version_info.txt',
)
