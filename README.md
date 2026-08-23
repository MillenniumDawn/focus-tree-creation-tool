# HOI4 Content Maker

> **A comprehensive GUI toolkit for creating Hearts of Iron IV mod content — no scripting knowledge required.**

![Python](https://img.shields.io/badge/Python-3.14%2B-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-Proprietary-red)
![Version](https://img.shields.io/badge/Version-2.0-gold)

---

## Overview

HOI4 Content Maker is a standalone Python/Tkinter desktop application that lets mod authors visually build and export Hearts of Iron IV game content. Instead of hand-writing Paradox script files, you work in purpose-built wizards that generate correct, wiki-accurate `.txt`, `.yml`, and scripted localisation files ready to drop into your mod.

### Wizards included

| Wizard | What it does |
|---|---|
| **Focus Tree Editor** | Visual drag-and-drop canvas for national focus trees. Place, connect, and configure focuses with a live code view. |
| **Decision Maker** | Full categories + decisions editor with live HOI4-themed preview, GFX icon picker, and import/export of existing `.txt` files. |
| **National Spirit Wizard** | Generates `ideas` blocks for national spirits/advisors with GFX browser. |
| **Dynamic Modifier Wizard** | Builds `dynamic_modifiers` entries with modifier pickers. |
| **Event Maker** | Multi-tab event editor with scripted localisation support, option builder, and effect picker. |

---

## Screenshots

> *Coming soon — contributions welcome.*

---

## Requirements

| Requirement | Notes |
|---|---|
| **Python 3.14 or newer** | Tested on Python 3.14. |
| **tkinter** | Included with most Python installations. See platform-specific notes below. |
| **Pillow** *(optional)* | Enables GFX icon previews (`.png`, `.tga`). Without it the app still runs, but icons show as placeholders. |
| **pillow-dds** *(optional)* | Adds `.dds` texture support for icon previews. |

### Platform-specific requirements

| Platform | tkinter | Notes |
|----------|---------|-------|
| **Windows** | Included with Python installer | Make sure "tcl/tk and IDLE" is checked during install |
| **macOS** | Included with python.org installer | Homebrew Python sometimes omits tkinter — use the official installer |
| **Linux** | Separate package | `sudo apt install python3-tk` (Debian/Ubuntu) or `sudo dnf install python3-tkinter` (Fedora) |

### Installing optional dependencies

Image preview support is declared as the `image` extra in `pyproject.toml`:

```bash
pip install ".[image]"
```

Or install individually:

```bash
pip install Pillow          # image previews
pip install pillow-dds      # .dds texture support
```

---

## Installation

### Option 1: Pre-built executable (no Python needed)

Download the latest release for your platform from the [Releases](../../releases) page:

| Platform | File |
|----------|------|
| Windows | `HOI4ContentMaker.exe` |
| macOS | `HOI4ContentMaker-mac` |
| Linux | `HOI4ContentMaker-linux` |

Just download and run — no Python installation required.

> Executables are not committed to the repository. Each tagged release is built by CI
> (`.github/workflows/ci.yml`), which runs the tests and linters first, and the binaries
> are attached to the [Releases](../../releases) page along with a `SHA256SUMS.txt` you
> can check them against.

### Option 2: Run from source

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/hoi4-content-maker.git
cd hoi4-content-maker

# 2. (Optional) Install image support
pip install ".[image]"

# 3. Run
python hoi4_content_maker.py
```

Running from a clone also picks up the `src/hoi4cm` package automatically — the entry
point adds `src/` to the import path at startup, so no install step is needed.

### Running tests and linters

```bash
pip install ".[dev]"
pytest                 # tests
ruff check .           # lint
black --check .        # formatting
```

`pyproject.toml` puts `src/` on the path for pytest, so the suite runs from a clean
checkout with no install. Tests live under `tests/`. Ruff and Black are scoped to the
`src/hoi4cm` package and `tests/` (the legacy monolith is excluded for now).

CI runs the same checks on every pull request, then builds the three executables
(`.github/workflows/ci.yml`). A `v*` tag runs that whole gate and publishes the binaries
to Releases, so a release can't skip the tests.

---

## Quick Start

1. **Launch** the app (`python hoi4_content_maker.py`).
2. **Load your mod** via *File → Load Mod Folder* (or the toolbar button). The app scans your mod for existing GFX, focus IDs, event IDs, and country tags automatically.
3. **Open a wizard** from the toolbar (Focus Tree, Decisions, Events, etc.).
4. **Build your content** using the visual editor.
5. **Export** — each wizard has dedicated export buttons that write the correct Paradox script files, or copy output to your clipboard.

Your work is **autosaved automatically** to a temp file. When you reopen a wizard you'll be prompted to restore your previous session.

---

## Wizards — Detailed Guide

### Focus Tree Editor

The main screen is the Focus Tree Editor — a zoomable, pannable canvas where you build national focus trees.

**Controls:**

| Action | Input |
|---|---|
| Place new focus | Right-click on canvas |
| Select focus | Left-click |
| Move focus | Left-click + drag |
| Multi-select | Ctrl + click |
| Pan | Ctrl + drag, or Middle Mouse Button drag |
| Zoom | Scroll wheel |
| Undo | Ctrl + Z |

**Features:**
- Live prerequisite lines drawn between focuses
- Mutex group linking (exclusive focus sets)
- Per-focus properties panel: ID, localisation, icon, cost, prerequisites, completion effects, AI weights
- GFX browser for picking focus icons from your mod's `gfx/interface/goals/`
- Inline code view with syntax highlighting
- Export to `national_focus/*.txt` and configured-language localisation YML

---

### Decision Maker

A three-panel editor: **category/decision tree** (left), **properties editor** (centre), **live preview** (right).

**Features:**
- Create and organise decision categories and decisions
- Drag-and-drop GFX icon picker
- Live HOI4-themed preview renders your decisions as they appear in-game
- HOI4 localisation token rendering (`[TAG:NameWithFlag]`, `§Y...§!` colour codes)
- Category visibility toggles — hide categories to reduce preview complexity while working
- **Solo** button — show only the currently selected category in the preview
- Import existing `.txt` decision files (preserves all fields)
- Export to `common/decisions/TAG_decisions.txt`, `common/decisions/categories/TAG_categories.txt`, and configured-language localisation YML
- Apply edits: paste/edit raw Paradox script directly in the Code tab and sync back to the editor
- Undo/redo support

**Country tag name mapping** (Settings → Country Tag Names):
- Map country tags to display names (`SOV` → `Soviet Union`) for readable preview rendering
- One-click "Load Vanilla Tags" fills ~45 common HOI4 tags

---

### National Spirit Wizard

Builds `ideas = { ... }` blocks for country-specific national spirits and advisors.

**Features:**
- Fields for slot, picture, modifier blocks, allowed/cancel triggers
- GFX browser integration
- Generates ready-to-paste ideas script and localisation

---

### Dynamic Modifier Wizard

Builds `dynamic_modifiers = { ... }` entries used for runtime modifiers.

---

### Event Maker

A full event authoring tool.

**Features:**
- Event type selector (country, news, state, unit leader)
- Option builder — add multiple options with individual effects
- Scripted localisation import/export
- Effect picker with autocomplete
- Live preview matching in-game event window appearance
- GFX background picker

---

## Settings

Access via *File → Settings* or the gear icon in the toolbar.

| Setting | Description |
|---|---|
| **Mod Root Path** | Override the auto-detected mod folder path |
| **HOI4 Localisation** | Choose the language used for localisation headers, folders, filenames, and discovery |
| **GFX Paths** | Customise where the app looks for goal icons, idea sprites, and event pictures |
| **Extra GFX Directories** | Add additional folders to scan for sprites |
| **Country Tag Names** | Map TAG codes to display names for the preview renderer |
| **Loc Token Style** | Choose colon-style `[SOV:NameWithFlag]` or dot-style `[SOV.GetName]` |
| **Event Dimension Profiles** | Define custom event image sizes for non-vanilla mods |

Settings are saved automatically to `~/.hoi4_focus_maker.json`.

---

## File Structure

```
hoi4_content_maker.py       ← application entry point (the GUI)
src/hoi4cm/                 ← modular package (logging + shared core)
  core/
    logger.py               ← logging setup, error buffer, excepthook
    config.py               ← persistent user config load/save
    paths.py                ← mod-dir defaults + tolerant file reading
hoi4_logger.py              ← back-compat shim → hoi4cm.core.logger
tests/                      ← pytest suite
  test_logger.py            ← logging module tests
pyproject.toml              ← dependencies (extras: image/dev/build), metadata, pytest config
README.md
CHANGELOG.md
BUILD_INSTRUCTIONS.md       ← how to compile executables
build/
  build.py                  ← cross-platform build script
  requirements.txt          ← hash-pinned build deps (pyinstaller, Pillow)
  build.bat                 ← Windows-only build script (legacy)
  build_encrypted.bat       ← Windows-only encrypted build (legacy)
  hoi4_content_maker.spec   ← PyInstaller spec (Windows)
  generate_icon.py          ← generates app icons (.ico, .png)
  version_info.txt          ← Windows file properties metadata
.github/workflows/
  ci.yml                    ← CI: lint, test, build; publishes to Releases on tag push
docs/
  FOCUS_TREE.md             ← Focus Tree Editor deep-dive
  DECISION_MAKER.md         ← Decision Maker deep-dive
  CONTRIBUTING.md           ← contribution guidelines
```

> The app is being split out of a single file into the `hoi4cm` package one module at
> a time. Logging and the shared core came first; `hoi4_content_maker.py` is still the
> launch point.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + Z` | Undo |
| `Ctrl + Y` | Redo |
| `Ctrl + S` | Save / export current wizard |
| `Ctrl + N` | New focus / decision |
| `Delete` | Delete selected item |
| `Ctrl + D` | Duplicate selected item |
| `Ctrl + A` | Select all (Focus Tree) |
| `Escape` | Deselect |

---

## Exporting to Your Mod

Each wizard produces one or more files:

```
your_mod/
├── common/
│   ├── national_focus/
│   │   └── TAG_focuses.txt          ← Focus Tree export
│   ├── decisions/
│   │   ├── TAG_decisions.txt        ← Decision Maker export
│   │   └── categories/
│   │       └── TAG_categories.txt   ← Decision Maker export
│   ├── ideas/
│   │   └── TAG_ideas.txt            ← National Spirit export
│   └── dynamic_modifiers/
│       └── TAG_modifiers.txt        ← Dynamic Modifier export
├── events/
│   └── TAG_events.txt               ← Event Maker export
└── localisation/
    └── <language>/
        └── TAG_l_<language>.yml      ← All wizards use the configured language
```

Use **Save to Mod** (where available) to write directly to the correct path inside your loaded mod folder, or use the **Export** / **Copy to Clipboard** buttons to place output manually.

---

## Troubleshooting

**Icons don't appear in the GFX picker or preview**
- Install Pillow: `pip install Pillow`
- For `.dds` files: `pip install pillow-dds`
- Make sure your mod folder is loaded (*File → Load Mod Folder*)

**"No module named tkinter"**
- Windows: reinstall Python and ensure "tcl/tk and IDLE" is checked in the installer
- Linux: `sudo apt install python3-tk`
- macOS: use the official python.org installer (Homebrew Python sometimes omits tkinter)

**Autosave restore shows empty tree**
- This was a known bug fixed in v2.0. Update to the latest version.

**App is slow with large mods**
- Use the category visibility toggles (👁 / 🚫 buttons) to hide categories you aren't currently editing
- The **Solo** button shows only one category at a time

---

## Contributing

This project is currently proprietary. Forks and redistribution are not permitted without explicit written permission from the author.

If you find a bug or have a feature request, please open an **Issue** on GitHub.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

---

## License

Copyright © 2025 Millennium Dawn Team. All Rights Reserved.

This software is **open-source**. See the licence header in `hoi4_content_maker.py` for full terms.

---

## Acknowledgements

- [Paradox Interactive](https://www.paradoxinteractive.com/) — creators of Hearts of Iron IV
- [HOI4 Modding Wiki](https://hoi4.paradoxwikis.com/) — reference for all script syntax
