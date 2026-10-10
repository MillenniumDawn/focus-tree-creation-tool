# Build Instructions

Use `build/build.py` to compile HOI4 Content Maker into a standalone executable.
The script supports Windows, macOS, and Linux.

## Requirements

- Python 3.14 or newer, with `tkinter` available.
- PyInstaller 6.22.2 or newer and Pillow. Install both from the project root:

  ```bash
  pip install ".[build]"
  ```

- On Linux, install the system tkinter package if needed:

  ```bash
  sudo apt-get install python3-tk    # Debian/Ubuntu
  sudo dnf install python3-tkinter   # Fedora
  ```

The executable smoke test opens Tk, so it needs a display. On a headless Linux
machine, install `xvfb` and run the smoke test under `xvfb-run` as shown below.

## Build

From the project root, run:

```bash
python build/build.py
```

The script detects the current platform, generates a temporary PyInstaller spec,
builds the executable in the repository root, and removes its temporary spec and
work directory afterward.

| Platform | Output |
| --- | --- |
| Windows | `HOI4ContentMaker.exe` |
| macOS | `HOI4ContentMaker-mac` |
| Linux | `HOI4ContentMaker-linux` |

Only the executable for the target platform needs to be distributed. Builds are
platform-specific, so build separately on each operating system.

## Smoke-test the executable

The `--smoke-test` option initializes Tcl, Tk, and ttk, then exits without opening
the editor. Use the matching command after building:

```powershell
.\HOI4ContentMaker.exe --smoke-test
```

```bash
./HOI4ContentMaker-mac --smoke-test
```

```bash
xvfb-run -a ./HOI4ContentMaker-linux --smoke-test
```

On Linux with a desktop session, `./HOI4ContentMaker-linux --smoke-test` can be
run directly instead.

## Build files

| File | Purpose |
| --- | --- |
| `build/build.py` | Current cross-platform PyInstaller build script |
| `build/requirements.txt` | Hash-pinned build dependencies used by CI |
| `build/generate_icon.py` | Generates the application icon files |
| `build/version_info.txt` | Windows executable version metadata |
| `pyproject.toml` | Project metadata and optional dependency groups |

## Automated builds and releases

`.github/workflows/ci.yml` runs linting and tests for pull requests and pushes to
`main`. For pull requests it also builds and smoke-tests executables on Windows,
macOS, and Linux. A push to `main` skips that build, because the pre-release
workflow below builds the same executables.
When a stable `vX.Y.Z` tag is pushed, CI runs the same checks and builds, then
publishes a GitHub Release with the three executables and `SHA256SUMS.txt`.
Stable release tags must use an even minor version; CI rejects tags on the odd
pre-release line and skips tags ending in `-pre.<attempt>`.

Stable releases are prepared by the release pull request workflow, not by
committing a tag or changing version files by hand. On pushes to `main`,
`.github/workflows/release-pr.yml` regenerates the `release/version-bump` branch
from `main` and, when there are unreleased changelog entries, opens or updates a
pull request. Merging that pull request updates the project version and
changelog. `.github/workflows/tag-release.yml` then checks that the project
version matches the changelog and pushes the corresponding `vX.Y.Z` tag. With
the configured GitHub App token, that tag starts the CI release job. The release
workflows fall back to `GITHUB_TOKEN` if the app token cannot be created, but
writes made with that token do not trigger downstream workflows.

The release pull request workflow can also be run manually with a `patch`,
`minor`, or `major` bump. Each push to `main` also starts
`.github/workflows/pre-release.yml`, which builds and publishes a GitHub
prerelease with the three executables and checksums. That workflow can be run
manually as well. Pre-release versions use the odd minor above the current
stable version, with the GitHub Actions run number as the patch; their tags end
in `-pre.<attempt>` and are not published by the stable release job.

## macOS notes

PyInstaller builds are not code-signed, so macOS may show a Gatekeeper warning.
Users can open the app using the right-click menu, or remove the quarantine flag
with `xattr -cr HOI4ContentMaker-mac`.
