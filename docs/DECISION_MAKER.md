# Decision Maker — Full Reference

The Decision Maker is a three-panel wizard for authoring HOI4 decision categories and decisions.

```
┌──────────────────┬─────────────────────────┬──────────────────────┐
│  CATEGORIES &    │  DECISION PROPERTIES     │  Preview / Chain /   │
│  DECISIONS       │  (editor)                │  Code                │
│  (tree)          │                          │                      │
└──────────────────┴─────────────────────────┴──────────────────────┘
```

---

## Opening the Wizard

From the main toolbar: **Decisions** button, or *Tools → Decision Maker*.

---

## The Tree Panel (Left)

Shows all your categories and their decisions in a collapsible tree.

### Category rows
- **▼ / ▶** — expand/collapse the category's decisions
- **GFX icon** (or 📁 if no icon is set / PIL not installed)
- **Display name** — pulled from the `loc_name` field, loc codes stripped
- **ID** — the `cat_id` in small monospace text
- **Count badge** — number of decisions in the category (gold = visible, grey = hidden)
- **👁 / 🚫 eye button** — toggle category visibility in the preview and exports

### Decision rows
- **GFX icon** (or 📋 fallback)
- **Display name** with PP cost badge

### Quick action buttons (above tree)

| Button | Action |
|---|---|
| `👁 All` | Make all categories visible in preview |
| `🚫 All` | Hide all categories from preview |
| `Solo` | Show only the currently selected category; hide all others |

**Solo** works whether a category or a decision is selected — if a decision is selected, Solo isolates its parent category.

### Search bar
Type to filter the tree by category ID, decision ID, or display name.

---

## The Properties Editor (Centre)

Clicking any category or decision in the tree loads it into the editor.

### Category fields

| Field | HOI4 key | Notes |
|---|---|---|
| Category ID | `cat_id` | Unique script ID, e.g. `TAG_my_category` |
| Display Name | localisation | Shown in-game. Supports `§Y...§!` colour codes |
| Description | localisation | Optional flavour text |
| Icon | `icon` | GFX key, e.g. `GFX_decision_category_generic` |
| Picture | `picture` | Large background image |
| Allowed | `allowed` | Trigger block — when the category exists |
| Visible | `visible` | Trigger block — when the category shows |
| Priority | `priority` | Numeric, default 1 |
| Visible When Empty | `visible_when_empty` | Checkbox |
| On Map Area | `on_map_area` | Map highlight block |
| Scripted GUI | `scripted_gui` | Optional GUI key |

### Decision fields

| Field | HOI4 key | Notes |
|---|---|---|
| Decision ID | `dec_id` | Unique script ID |
| Display Name | localisation | |
| Description | localisation | |
| Icon | `icon` | GFX key |
| Allowed | `allowed` | Once-only trigger (game start) |
| Visible | `visible` | Per-frame show/hide trigger |
| Available | `available` | Per-frame enable/grey-out trigger |
| Cost | `cost` | PP cost (default 25) |
| Days Remove | `days_remove` | Duration before auto-removal |
| Days Re-Enable | `days_re_enable` | Cooldown after removal |
| Fire Only Once | `fire_only_once` | Checkbox |
| Is Mission | `is_mission` | Checkbox — turns decision into a timed mission |
| Complete Effect | `complete_effect` | Script block run on completion |
| Remove Effect | `remove_effect` | Script block run on removal |
| Cancel Effect | `cancel_effect` | Script block run on cancellation |
| Modifier | `modifier` | Applied while decision is active |
| AI Will Do | `ai_will_do` | AI weight block |
| Target Array | `target_array` | For targeted decisions |
| Priority | `priority` | Display ordering |

---

## The Right Panel

Three tabs switchable at the top:

### Preview tab
Renders your decisions as a close approximation of the in-game decision screen. Includes:
- Category header with picture and description
- Decision rows with icons, names, and cost badges
- Colour codes (`§Y`, `§R`, etc.) rendered in correct colours
- Loc tokens resolved: `[SOV:NameWithFlag]` → `Soviet Union`, `[NKO]Korea` → `North Korea`

### Chain View tab
Visualises decision chains (group tag relationships).

### Code tab
Shows the raw Paradox script that will be generated.

**Apply Edits** button: edit the code directly in this tab and click Apply to sync the changes back into the editor. The parser will re-import all categories and decisions from the raw text.

---

## Toolbar Buttons

| Button | Action |
|---|---|
| `+ New Category` | Create a new empty category |
| `+ New Decision` | Create a new decision under the selected category |
| `Import .txt` | Import an existing decisions `.txt` file from your mod |
| `Import .yml loc` | Import a localisation `.yml` to populate display names |
| `Import scripted_loc` | Import a scripted localisation file |
| `Export .txt` | Export decisions and categories to `.txt` files |
| `Copy .yml` | Copy localisation YAML to clipboard |
| `Save to Mod` | Write files directly into the loaded mod folder |
| `Undo` | Step back through the change history |

---

## Country Tag Names

Go to **Settings → Country Tag Names** to map country codes to display names.

This affects how loc tokens render in the preview:
- Without mapping: `[SOV:NameWithFlag]` → `SOV`
- With mapping (`SOV` = `Soviet Union`): → `Soviet Union`

Click **⚡ Load Vanilla Tags** to pre-fill ~45 common HOI4 country codes.

---

## Visibility & Performance

For mods with many categories and decisions, the preview can become slow to render. Use the visibility system to work on one category at a time:

1. Click **Solo** to hide everything except the selected category.
2. Edit decisions in the centre panel — the preview only renders the visible category.
3. Click **👁 All** when you need to see the full picture again.

Hidden categories are **not exported** in the decisions or categories `.txt` files (so you can work on sections without accidentally exporting incomplete work). However, hidden categories **are** included in localisation exports so you never lose `.yml` keys.

---

## Import / Export Reference

### Import `.txt`
Parses a HOI4 decisions file. Supports:
- Category blocks with all standard fields
- Nested decision blocks
- Auto-discovery of `.yml` localisation in the same folder hierarchy

Imported data merges into the current session. Existing categories with matching IDs are updated, not duplicated.

### Export `.txt`
Produces two files:
- `TAG_decisions.txt` — the decisions file (categories containing decision blocks)
- `TAG_categories.txt` — the categories file (category metadata only)

### Copy `.yml`
Copies a `l_english:` YAML block with all `name:0` and `desc:0` keys for every category and decision.

### Save to Mod
Writes output directly to your mod's `common/decisions/` and `localisation/` folders (requires a mod to be loaded).

---

## Autosave

The Decision Maker autosaves to a temp file every time you make a change. When you reopen the wizard you'll be prompted:

> *"An autosave was found with N categories and N decisions. Restore it?"*

Click **Yes** to restore your previous session. The tree, editor, and preview all reload correctly.

To start fresh, click **No** — the autosave file is not deleted, so you can reopen the wizard again if you change your mind.
