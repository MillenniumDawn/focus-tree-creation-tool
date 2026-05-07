# Build Instructions

How to compile `hoi4_content_maker.py` into a standalone executable that:
- Requires **no Python installation** on the user's machine
- Works on **Windows, macOS, and Linux**
- Shows **no CMD/terminal window** when launched
- Has **bytecode protection** so the source code is not trivially readable

---

## One-time setup (your machine only)

Open a terminal and run:

```bash
pip install -r requirements-build.txt
```

This installs PyInstaller and Pillow. You only need to do this once.

On **Linux**, you also need tkinter (not bundled with pip):
```bash
sudo apt-get install python3-tk    # Debian/Ubuntu
sudo dnf install python3-tkinter   # Fedora
```

---

## Building

### Cross-platform build (recommended)

From the project root:

```bash
python build/build.py              # standard build
python build/build.py --encrypted  # AES-encrypted bytecode
```

This auto-detects your platform and produces the correct output:

| Platform | Output |
|----------|--------|
| Windows | `HOI4ContentMaker.exe` |
| macOS | `HOI4ContentMaker-mac` |
| Linux | `HOI4ContentMaker-linux` |

### Windows-only build (legacy)

If you prefer the old Windows `.bat` scripts:

```
Double-click:  build/build.bat
```

Or from the terminal:
```bat
build\build.bat
```

### Encrypted build (stronger protection)

This build AES-encrypts the bytecode inside the executable. Anyone who extracts the bundle gets encrypted `.pyc` files — not readable Python.

```bash
python build/build.py --encrypted
```

Or on Windows (legacy): `build\build_encrypted.bat`

> **Note:** The encryption key is hardcoded. Change the key string before building. Keep it private — don't commit it to GitHub.

---

## What each file does

| File | Purpose |
|---|---|
| `build/build.py` | Cross-platform build script (Windows, macOS, Linux) |
| `build/build.bat` | Windows-only one-click build script (legacy) |
| `build/build_encrypted.bat` | Windows-only encrypted bytecode build (legacy) |
| `build/hoi4_content_maker.spec` | PyInstaller spec for Windows `.bat` builds |
| `build/version_info.txt` | Windows file properties (right-click → Properties) |
| `build/generate_icon.py` | Generates `icon.ico` and `icon.png` automatically |
| `requirements.txt` | Optional runtime dependencies (Pillow) |
| `requirements-build.txt` | Build dependencies (PyInstaller, Pillow) |
| `.github/workflows/release.yml` | CI workflow — auto-builds and publishes releases |

---

## Using your own icon

Replace `icon.ico` with any `.ico` file before running the build. A 256×256 icon is recommended. You can create one from a PNG at [icoconvert.com](https://icoconvert.com) or using image editors like GIMP or Photoshop.

---

## Build output

```
your-folder/
├── HOI4ContentMaker.exe       ← Windows (distribute this)
├── HOI4ContentMaker-mac       ← macOS (distribute this)
├── HOI4ContentMaker-linux     ← Linux (distribute this)
└── build/                     ← build scripts (not output)
```

Only the executable for your platform needs to be distributed. Temp files are cleaned up automatically by `build.py`.

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

## Cross-Platform Build (Windows / macOS / Linux)

A Python build script replaces the Windows-only `.bat` files. It works on all platforms:

```bash
python build/build.py              # standard build
python build/build.py --encrypted  # AES-encrypted bytecode
```

### One-time setup

```bash
pip install -r requirements-build.txt
```

On **Linux**, you also need tkinter:
```bash
sudo apt-get install python3-tk    # Debian/Ubuntu
sudo dnf install python3-tkinter   # Fedora
```

### Output per platform

| Platform | Output file | Size |
|----------|------------|------|
| Windows | `HOI4ContentMaker.exe` | ~18 MB |
| macOS | `HOI4ContentMaker-mac` | ~18 MB |
| Linux | `HOI4ContentMaker-linux` | ~18 MB |

### Automated releases (CI)

Every push to `main` that changes `hoi4_content_maker.py` triggers a GitHub Actions workflow that:
1. Extracts the version from the source header (e.g., `Version 2.0`)
2. Creates a git tag like `v2.0.1`, `v2.0.2`, etc.
3. Builds executables on Windows, macOS, and Linux
4. Publishes all three binaries as a GitHub Release

You can also trigger a release manually from the Actions tab (`workflow_dispatch`).

### macOS notes

- PyInstaller builds will trigger Gatekeeper warnings without code signing
- Users can bypass with: right-click > Open, or `xattr -cr HOI4ContentMaker-mac`

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
