import ast

from source_scan import ROOT, SOURCE_PATHS, source_calls


def test_source_inventory_keeps_sorted_package_and_monolith():
    assert SOURCE_PATHS == (
        *sorted((ROOT / "src" / "hoi4cm").rglob("*.py")),
        ROOT / "hoi4_content_maker.py",
    )
    assert len(SOURCE_PATHS) == len(set(SOURCE_PATHS))


def test_source_calls_preserves_ast_walk_order_and_locations(tmp_path):
    path = tmp_path / "calls.py"
    source = '\ntr("key", "Value")\nobj.record("label", nested())\n'
    path.write_text(source, encoding="utf-8")
    expected = [
        node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)
    ]

    calls = source_calls(path)

    assert [ast.dump(node, include_attributes=True) for node in calls] == [
        ast.dump(node, include_attributes=True) for node in expected
    ]
    assert calls is source_calls(path)


def test_source_calls_accepts_files_without_calls(tmp_path):
    path = tmp_path / "empty.py"
    path.write_text("value = 1\n", encoding="utf-8")

    assert source_calls(path) == ()
