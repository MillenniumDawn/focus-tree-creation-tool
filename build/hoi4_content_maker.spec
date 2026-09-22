# -*- mode: python ; coding: utf-8 -*-
# HOI4 Content Maker — PyInstaller spec

block_cipher = None

a = Analysis(
    ['..\\hoi4_content_maker.py'],
    pathex=['..', '..\\src'],
    binaries=[],
    datas=[('..\\locales', 'locales')],
    hiddenimports=[
        'hoi4cm', 'hoi4cm.core', 'hoi4cm.core.logger',
        'hoi4cm.core.config', 'hoi4cm.core.paths', 'logging.handlers',
        # The wizard entry points are resolved lazily at runtime.
        'hoi4cm.wizards.national_spirit', 'hoi4cm.wizards.decision',
        'hoi4cm.wizards.dyn_mod', 'hoi4cm.wizards.additional_income',
        'hoi4cm.wizards.event',
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
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

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
