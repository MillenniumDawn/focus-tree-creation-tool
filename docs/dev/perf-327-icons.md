# Structured icons (#327)

`Focus.gfx` remains a string for sidebar/image lookup. Conditional blocks and
ordered repeated declarations live in private semantic `_icon_script` metadata,
preserved by project recovery, undo and Code-tab application. Assigning a different
scalar gfx explicitly replaces the imported script; assigning the unchanged preview
retains it. The canonical icon renderer is shared by all exporters.

Run `pytest tests/test_focus_icons.py tests/test_focus_tree_codec.py
 tests/test_project_codec.py tests/test_undo.py`. The focused regression exercises
import, unrelated edit, JSON recovery, undo restoration, Code-tab apply, and main,
wrapped, shared and joint exports. Independent review of the public MD aggregate
(26,245 focuses) verified all 28 conditional blocks and one repeated declaration
preserve their parsed icon values; baseline project decoding lost all 29.
