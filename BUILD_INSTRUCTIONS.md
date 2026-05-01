# Build Instructions

How to compile `hoi4_content_maker.py` into a standalone Windows `.exe` that:
- Requires **no Python installation** on the user's machine
- Shows **no CMD window** when launched
- Has your **name and version** in the Windows file properties
- Has **bytecode protection** so the source code is not trivially readable

---

## One-time setup (your machine only)

Open a terminal and run:

```bat
pip install pyinstaller
pip install Pillow
```

That's it. You only need to do this once.

---

## Building

### Standard build (recommended for most releases)

```
Double-click:  build.bat
```

Or from the terminal:
```bat
build.bat
```

Output: **`HOI4ContentMaker.exe`** in the same folder.

---

### Encrypted build (stronger protection)

This build AES-encrypts the bytecode inside the `.exe`. Anyone who extracts the bundle gets encrypted `.pyc` files — not readable Python.

```
Double-click:  build_encrypted.bat
```

Extra requirement (installed automatically by the script):
```bat
pip install "pyinstaller[encryption]"
```

> **Note:** The encryption key is hardcoded in `build_encrypted.bat`. Change the line `key = 'HOI4CM_BLAZER_2025'` to your own secret string before building. Keep this string private — don't commit it to GitHub.

---

## What each file does

| File | Purpose |
|---|---|
| `build.bat` | Standard one-click build script |
| `build_encrypted.bat` | Encrypted bytecode build |
| `hoi4_content_maker.spec` | PyInstaller spec — controls exactly how the `.exe` is built |
| `version_info.txt` | Windows file properties (name, version, copyright shown in right-click → Properties) |
| `generate_icon.py` | Generates `icon.ico` automatically if it doesn't exist |
| `icon.ico` | App icon (auto-generated, or replace with your own) |

---

## Using your own icon

Replace `icon.ico` with any `.ico` file before running the build. A 256×256 icon is recommended. You can create one from a PNG at [icoconvert.com](https://icoconvert.com) or using image editors like GIMP or Photoshop.

---

## Build output

```
your-folder/
├── HOI4ContentMaker.exe    ← distribute this file
├── dist/                   ← PyInstaller output (same .exe, safe to delete)
└── build/                  ← temp files (deleted automatically)
```

Only **`HOI4ContentMaker.exe`** needs to be distributed. The `dist/` folder is cleaned up automatically.

---

## Protection level comparison

| Method | CMD window | Source readable? | Size |
|---|---|---|---|
| Running `.py` directly | Yes | Yes (it's the source) | — |
| `build.bat` (standard) | **No** | Bytecode only (harder to read) | ~15–25 MB |
| `build_encrypted.bat` | **No** | **AES-encrypted bytecode** | ~20–30 MB |

### Important notes on protection

PyInstaller + encryption is **not perfect protection** — a determined reverse-engineer with enough time can still extract code. However it:

- Stops casual inspection (`python -c "import dis"` etc.)
- Makes the code significantly harder to read or modify
- Prevents the tool from being run as a `.py` file (users get an `.exe`)
- Hides your internal logic, algorithms, and any API keys

For a modding tool like this, the encrypted build is more than sufficient to deter casual copying.

---

## Troubleshooting

**"Failed to execute script" when running the .exe**
- Run `build.bat` from a terminal to see the full error output
- Make sure `hoi4_content_maker.py` is in the same folder as `build.bat`

**`.exe` triggers Windows Defender / antivirus**
- This is common with PyInstaller builds (false positive)
- Code-signing with a certificate eliminates this, but certificates cost money
- Users can add an exception in Windows Security

**Build is very slow on first run**
- Normal — PyInstaller is building a Python runtime. Subsequent builds are faster.
- The encrypted build is slower because it compiles the AES extension

**`tinyaes` fails to install**
- You need a C compiler. Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) and try again
- Or use the standard `build.bat` instead

**Icon doesn't appear on the .exe**
- Windows caches icons aggressively. Try: right-click desktop → Refresh, or log out and back in
- Or run: `ie4uinit.exe -show` in a terminal to flush the icon cache
