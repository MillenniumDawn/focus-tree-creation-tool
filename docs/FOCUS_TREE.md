# Focus Tree Editor — Full Reference

The Focus Tree Editor is the main screen of HOI4 Content Maker. It provides a visual drag-and-drop canvas for building national focus trees.

---

## Canvas Controls

| Action | Input |
|---|---|
| Place new focus | Right-click on empty canvas |
| Select focus | Left-click |
| Deselect | Escape or click empty canvas |
| Move focus | Left-click + drag |
| Multi-select | Ctrl + click |
| Box-select | Click + drag on empty canvas |
| Pan canvas | Ctrl + drag, or Middle Mouse Button drag |
| Zoom in/out | Scroll wheel |
| Undo | Ctrl + Z |
| Redo | Ctrl + Y |
| Delete selected | Delete key |
| Duplicate selected | Ctrl + D |
| Select all | Ctrl + A |

---

## Focus Properties Panel

Selecting a focus opens its properties in the right-side panel.

### Identity
| Field | HOI4 key | Notes |
|---|---|---|
| Focus ID | `id` | Unique identifier, e.g. `TAG_my_focus` |
| Icon | `icon` | GFX key from `gfx/interface/goals/` |
| X Position | `x` | Grid column (relative or absolute) |
| Y Position | `y` | Grid row |
| Cost | `cost` | In Political Power, default 10 (70 days at 1PP/day) |

### Localisation
| Field | Notes |
|---|---|
| Display Name | Shown in-game focus tree |
| Description | Tooltip text |

### Prerequisites
- Add prerequisite focuses using the prerequisite picker
- Choose AND (all required) or OR (any one required)

### Mutually Exclusive
- Link focuses that cannot be taken together

### Completion Reward
The script block that fires when the focus is completed.

### Bypass
Optional trigger block — if true, the focus is auto-bypassed.

### Available
Trigger block — when the focus can be taken.

### Cancel Conditions
Trigger block — if true while the focus is active, it cancels.

### Select Effect / Cancel Effect
Script blocks run on selection and on cancellation respectively.

### AI Will Do
AI weight block controlling how likely the AI is to pick this focus.

---

## Connecting Focuses

### Prerequisites
1. Select the focus that should have a prerequisite.
2. In the Properties panel, click **Add Prerequisite**.
3. Click the focus (or focuses) that must be completed first.
4. Lines are drawn automatically on the canvas.

### Mutex Groups
1. Select a focus.
2. Click **Set Mutex Group** in the Properties panel.
3. Click the other focus(es) that are mutually exclusive.
4. Red lines indicate mutex relationships on the canvas.

---

## GFX Browser

Click the icon field's **Browse** button to open the GFX browser.

- Shows all sprites found in your mod's `gfx/interface/goals/` folder (and any extra GFX directories configured in Settings)
- Filter by name
- Click a sprite to select it — the focus icon updates immediately on the canvas
- Supports `.png`, `.tga`, and `.dds` (DDS requires `pillow-dds`)

---

## Code View

The **Code** tab in the right panel shows the raw Paradox script for the selected focus. The full tree script is available via **Export → Export .txt**.

---

## Export

### Export .txt
Writes a `national_focus/*.txt` file with the complete focus tree.

### Export .yml
Writes a `localisation/*_l_english.yml` file with all focus display names and descriptions.

### Save to Mod
Writes both files directly into your loaded mod folder at the correct paths.

### Copy to Clipboard
Copies the raw script to your clipboard for manual pasting.

---

## Tips

**Using relative X positions:**
HOI4 supports `relative_position_id` to position focuses relative to another focus. Set a focus's X/Y to 0 and use the relative position field to anchor it to a parent focus. This makes reorganising trees much easier.

**Focus prefixes:**
The app auto-detects your country tag from existing focus IDs in your loaded mod and pre-fills the prefix field (e.g. `GER_` for a German focus tree).

**Large trees:**
Use zoom out (scroll wheel) to see the full tree. Use Ctrl+A to select all focuses and drag to reposition the whole tree.

**Undo history:**
Up to 60 undo steps are kept per session.
