"""Source inventory and call nodes shared by repository guards."""

import ast
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    *sorted((ROOT / "src" / "hoi4cm").rglob("*.py")),
    ROOT / "hoi4_content_maker.py",
)


@cache
def source_calls(path: Path) -> tuple[ast.Call, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return tuple(node for node in ast.walk(tree) if isinstance(node, ast.Call))
