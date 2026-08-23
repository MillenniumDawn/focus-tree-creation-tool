# Security hardening pass

Date: 2026-07-02. Branch: `chore/security-review-and-hardening`.

## Why

The app opens Hearts of Iron IV mod files (`.txt`, `.yml`, `.gfx`, `.drawio`) that
users download and share. Those files are untrusted input. This pass audited the
whole app for ways a booby-trapped mod (or diagram) could harm the person who
opens it, closed the real gaps, and fixed two algorithmic slow paths found along
the way. All new logic lives in `src/hoi4cm/core/`, keeping with the "don't grow
the monolith" rule. Each helper ships with a test.

## What the audit found clean

No code execution, command injection, network exfiltration, or ReDoS. The app is
stdlib + tkinter only, uses no `eval`/`exec`/`pickle`/`yaml.load`, makes no
outbound network calls, and its parsers walk brace depth character by character
rather than with backtracking regex. Config, logger, and the SQLite scan cache
were clean. So the work below is about bounding untrusted input, not plugging an
active exploit.

## Security fixes

### Path traversal via unsanitized IDs and tags

Output filenames were built straight from IDs and tags, some of which come from
parsed (untrusted) mod content. A value like `../../evil` could escape the
intended folder. The clearest case: the focus-tree exporter builds
`MD_focus_{country_tag}_l_{language}.yml` where `country_tag` falls back to a
tag parsed from the imported file with only `.upper().strip()`.

Fix: new `src/hoi4cm/core/safe_path.py`.

- `sanitize_component(name, fallback="unnamed")` reduces a value to a single safe
  path segment. Drops any directory prefix, whitelists `[A-Za-z0-9_.-]`, and
  rejects `""`/`.`/`..`. Valid HOI4 IDs (already `[A-Za-z0-9_]`) pass through
  unchanged, so nothing legitimate breaks.
- `safe_join(base, *parts)` joins and then confirms the resolved path stays inside
  `base` (via `realpath` + `commonpath`), raising `ValueError` on escape. Available
  for defense in depth.

Wired into the focus-tree loc export (`hoi4_content_maker.py`) and every wizard
that turns an ID into a filename: `national_spirit.py` (`sid`), `decision.py`
(`ns` from `cat_id`), `event.py` (`ns` from `eid`), `additional_income.py`
(`idea_id`), `dyn_mod.py` (`mid`).

### Draw.io import: decompression bomb + XML entity expansion

`_import_drawio` inflated the embedded, zlib-compressed XML of a `.drawio` file
with no size cap, then parsed it with stock `ElementTree`. A tiny file could
inflate to gigabytes (memory exhaustion), and a DTD with nested entities could
blow up parsing (billion laughs).

Fix: new `src/hoi4cm/core/safe_xml.py`.

- `bounded_inflate(data, ...)` inflates with a 64 MB cap and raises `ValueError`
  past it.
- `safe_fromstring(xml_str, ...)` rejects oversize input and refuses any
  `<!DOCTYPE`/`<!ENTITY` markup before parsing, which blocks entity expansion.
  (Modern `ElementTree` no longer exposes its expat handlers across Python
  versions, so the check scans the markup directly. Both tokens are case-sensitive
  per the XML spec and only appear as literal markup, so the substring check is
  reliable. Legit Draw.io files never declare a DTD.)

The importer also caps the raw file read at 64 MB before parsing. Both caps sit
far above any real diagram.

### `read_file` had no size cap

`src/hoi4cm/core/paths.py:read_file` read whole files into memory and is fanned
across up to 8 threads during a mod scan. A huge file, or a symlink to
`/dev/zero`, could exhaust memory. Added a `max_bytes` cap (default 32 MB,
generous for mod files) that checks size first and bounds the read itself, so a
streaming pseudo-file is caught too. Oversize files are skipped and logged. The
new argument defaults on, so existing callers are unaffected.

### Config write is now atomic

`cfg_save` truncated then rewrote `~/.hoi4_focus_maker.json`, so a crash or full
disk mid-write left a corrupt config. It now writes a temp file in the same
directory, `fsync`s, and `os.replace`s it into place (atomic), cleaning up the
temp file on failure. The file is also `chmod`ed to `0600`.

### Pillow auto-install is now opt-in

On first launch without Pillow, `image.py` silently ran `pip install Pillow` at
import time. That is an unexpected network install and a supply-chain surface.
It now only runs if `HOI4CM_AUTO_INSTALL_PILLOW` is set; otherwise it logs a
one-line hint and falls back to placeholder icons (the existing no-Pillow path).
Frozen binaries never install.

### Wizard autosave moved out of /tmp

Four wizards autosaved working state to fixed-name files in the shared temp dir
(`/tmp/hoi4_cm_*_autosave.json`). On a multi-user host another user could
pre-plant those paths as symlinks and clobber a file the victim can write. New
`paths.autosave_path(name)` puts autosaves under `~/.hoi4cm/autosave/` (created
user-only, `0700`). Old `/tmp` autosaves simply won't be found on next open,
which is fine for best-effort recovery.

## CI / supply chain (`.github/workflows/release.yml`)

> Follow-up, issue #54: `release.yml` is gone. `ci.yml` is now the one workflow:
> lint and test on every push and PR, then the three-platform build, then a
> `release` job gated on `startsWith(github.ref, 'refs/tags/v')`. A tag can no
> longer publish binaries that skipped pytest, ruff, and black. CI's own actions
> are pinned to the same SHAs listed below, build deps come from a hash-pinned
> `build/requirements.txt`, and every release carries `SHA256SUMS.txt`.

- Least privilege. The workflow granted `contents: write` to every job, including
  `build`, which runs arbitrary project build code across three runners. Now the
  default is `contents: read`, `build` is explicitly read-only, and only the
  `release` job that publishes gets `contents: write`.
- Actions pinned to commit SHAs (with a version comment) instead of mutable tags,
  so a re-pointed or compromised tag can't inject code into the release. Same
  major versions as before, latest patch: checkout v4.3.1, setup-python v5.6.0,
  upload-artifact v4.6.2, download-artifact v4.3.0, action-gh-release v2.6.2.

## Performance

The app was already well optimized (dirty-key canvas redraws, SQLite scan cache,
parallel reads). Two real algorithmic slow paths fixed:

- Focus-tree export resolved `relative_position_id` by scanning all focuses per
  focus, O(F^2) on large trees. Now builds a name to focus map once, O(F).
  (`src/hoi4cm/focus_tree/export.py`)
- The duplicate-focus name loop rebuilt the set of existing names on every
  iteration. Built once before the loop. (`hoi4_content_maker.py`)

Assessed and left alone: the collision checks in the focus-apply handlers run
once per user click, not per frame, so their O(F) scan is negligible. The
left-panel focus-list rebuild is the biggest per-action UI cost, but it is only
called when the list content actually changed (selection-only updates already use
a cheaper path), and the only real win is widget diffing, a risky rewrite that
would grow the monolith. Left as a documented follow-up.

## Residual risk (not fixed here)

- Released binaries are unsigned. Signing needs certificates and repo secrets, so
  it stays out of scope. The open lower bounds and missing checksums were closed
  by issue #54 (see the CI section). What remains on that path is
  `build/build.py`'s `ensure_package()`, which would `pip install` an unpinned
  pyinstaller or Pillow if the import were missing. It never fires in CI, because
  the workflow installs the hash-pinned set first.
- Log files and the config are written with the default umask apart from the
  config's `0600`. They hold only local paths, not secrets.

## New helper API

| Function | Module | Purpose |
|---|---|---|
| `sanitize_component(name, fallback)` | `core.safe_path` | ID/tag to one safe path segment |
| `safe_join(base, *parts)` | `core.safe_path` | join and verify inside `base` |
| `bounded_inflate(data, ...)` | `core.safe_xml` | inflate with size cap |
| `safe_fromstring(xml_str, ...)` | `core.safe_xml` | parse XML, reject DTD/oversize |
| `read_file(path, max_bytes=...)` | `core.paths` | tolerant read with size cap |
| `autosave_path(name)` | `core.paths` | per-user autosave path under `~/.hoi4cm` |

All are re-exported from `hoi4cm.core`.

## Verification

- `pytest` (146 passing, adds `test_safe_path.py`, `test_safe_xml.py`,
  `test_image.py`, plus config/paths extensions).
- `ruff check .` and `black --check .` clean on `src/` and `tests/`.
- Manual: a >64 MB-inflating payload raises; a billion-laughs DOCTYPE is rejected;
  a real `.drawio` still imports; `read_file` on a >32 MB file returns empty and
  logs; sanitizer maps traversal payloads to a single safe segment and leaves
  valid IDs unchanged.
