"""Tests for hoi4cm.focus_tree.drawio — mxGraph XML -> HOI4 focus data."""

import base64
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

import pytest

from hoi4cm.focus_tree.drawio import (
    EmptyDrawioGraphError,
    build_drawio_focuses,
    clean_label,
    drawio_to_focus_data,
    parse_drawio_graph,
)
from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def _cell_xml(cells):
    body = "\n".join(cells)
    return f"<mxGraphModel><root>{body}</root></mxGraphModel>"


TWO_NODE_EDGE = _cell_xml(
    [
        '<mxCell id="0"/>',
        '<mxCell id="1" parent="0"/>',
        '<mxCell id="2" value="Focus A" vertex="1" parent="1">'
        '<mxGeometry x="0" y="0" width="120" height="60"/></mxCell>',
        '<mxCell id="3" value="Focus B" vertex="1" parent="1">'
        '<mxGeometry x="200" y="0" width="120" height="60"/></mxCell>',
        '<mxCell id="4" edge="1" source="2" target="3" parent="1"/>',
    ]
)


def _raw_deflate(data):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def _compress_page(inner_xml):
    quoted = urllib.parse.quote(inner_xml)
    return base64.b64encode(_raw_deflate(quoted.encode("utf-8"))).decode("ascii")


def test_clean_label_strips_html_and_sanitizes():
    # "&" sits between two underscores from the surrounding whitespace, and
    # since "&" itself gets dropped (not replaced with "_"), they don't merge.
    assert clean_label("<b>Air &amp; Sea</b>") == "Air__Sea"
    assert clean_label("  multi   word - label  ") == "multi_word_label"
    assert clean_label("weird!@# chars") == "weird_chars"
    assert clean_label("") == ""


def test_parse_drawio_graph_basic_vertices_and_edge():
    graph = parse_drawio_graph(TWO_NODE_EDGE)
    assert set(graph.vertices) == {"2", "3"}
    assert graph.vertices["2"].label == "Focus_A"
    assert graph.vertices["3"].x == 200.0
    assert graph.edges == [("2", "3")]


def test_parse_drawio_graph_unlabeled_shape_gets_fallback_name():
    xml = _cell_xml(
        [
            '<mxCell id="0"/>',
            '<mxCell id="1" parent="0"/>',
            '<mxCell id="9" vertex="1" parent="1">'
            '<mxGeometry x="0" y="0" width="10" height="10"/></mxCell>',
        ]
    )
    graph = parse_drawio_graph(xml)
    assert graph.vertices["9"].label == "focus_9"


def test_parse_drawio_graph_ignores_edge_to_unknown_vertex():
    xml = _cell_xml(
        [
            '<mxCell id="0"/>',
            '<mxCell id="1" parent="0"/>',
            '<mxCell id="2" value="A" vertex="1" parent="1">'
            '<mxGeometry x="0" y="0" width="10" height="10"/></mxCell>',
            '<mxCell id="5" edge="1" source="2" target="999" parent="1"/>',
        ]
    )
    graph = parse_drawio_graph(xml)
    assert graph.edges == []


def test_parse_drawio_graph_user_object_wrapper_overrides_label():
    xml = _cell_xml(
        [
            '<mxCell id="0"/>',
            '<mxCell id="1" parent="0"/>',
            '<UserObject id="5" label="My Focus">'
            '<mxCell vertex="1" parent="1">'
            '<mxGeometry x="5" y="5" width="100" height="50"/></mxCell>'
            "</UserObject>",
        ]
    )
    graph = parse_drawio_graph(xml)
    assert graph.vertices["5"].label == "My_Focus"


def test_parse_drawio_graph_empty_diagram_raises():
    xml = _cell_xml(['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>'])
    with pytest.raises(EmptyDrawioGraphError):
        parse_drawio_graph(xml)


def test_parse_drawio_graph_malformed_xml_raises_parse_error():
    with pytest.raises(ET.ParseError):
        parse_drawio_graph("<mxGraphModel><root>")


def test_parse_drawio_graph_rejects_doctype():
    bomb = (
        "<?xml version='1.0'?><!DOCTYPE lolz [<!ENTITY lol 'lol'>]>"
        "<mxGraphModel><root/></mxGraphModel>"
    )
    with pytest.raises(ValueError):
        parse_drawio_graph(bomb)


def test_parse_drawio_graph_handles_compressed_page():
    inner = (
        "<mxGraphModel><root>"
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="2" value="Compressed" vertex="1" parent="1">'
        '<mxGeometry x="10" y="10" width="80" height="40"/></mxCell>'
        "</root></mxGraphModel>"
    )
    wrapper = (
        '<mxfile><diagram id="p1" name="Page-1">'
        f"{_compress_page(inner)}</diagram></mxfile>"
    )
    graph = parse_drawio_graph(wrapper)
    assert graph.vertices["2"].label == "Compressed"


def test_drawio_to_focus_data_applies_prefix_and_grid():
    graph = parse_drawio_graph(TWO_NODE_EDGE)
    result = drawio_to_focus_data(graph, "TAG_")
    labels = {f.cid: f.label for f in result.focuses}
    assert labels == {"2": "TAG_Focus_A", "3": "TAG_Focus_B"}
    # Both nodes are on the same pixel row, so they land on the same grid
    # row and different (even) columns.
    positions = {f.cid: (f.x, f.y) for f in result.focuses}
    assert positions["2"][1] == positions["3"][1]
    assert positions["2"][0] % 2 == 0 and positions["3"][0] % 2 == 0
    assert positions["2"][0] != positions["3"][0]
    assert result.edges == [("2", "3")]
    assert result.auto_shifted == []


def test_drawio_to_focus_data_does_not_double_prefix():
    xml = _cell_xml(
        [
            '<mxCell id="0"/>',
            '<mxCell id="1" parent="0"/>',
            '<mxCell id="2" value="TAG_Already" vertex="1" parent="1">'
            '<mxGeometry x="0" y="0" width="10" height="10"/></mxCell>',
        ]
    )
    graph = parse_drawio_graph(xml)
    result = drawio_to_focus_data(graph, "TAG_")
    assert result.focuses[0].label == "TAG_Already"


def test_drawio_to_focus_data_does_not_mutate_input_graph():
    graph = parse_drawio_graph(TWO_NODE_EDGE)
    drawio_to_focus_data(graph, "TAG_")
    assert graph.vertices["2"].label == "Focus_A"


def test_drawio_to_focus_data_resolves_overlap():
    # Two shapes at the exact same pixel position collide on the same grid
    # slot; the second one (row/col sort tiebreak) must get auto-shifted.
    xml = _cell_xml(
        [
            '<mxCell id="0"/>',
            '<mxCell id="1" parent="0"/>',
            '<mxCell id="2" value="A" vertex="1" parent="1">'
            '<mxGeometry x="0" y="0" width="10" height="10"/></mxCell>',
            '<mxCell id="3" value="B" vertex="1" parent="1">'
            '<mxGeometry x="0" y="0" width="10" height="10"/></mxCell>',
        ]
    )
    graph = parse_drawio_graph(xml)
    result = drawio_to_focus_data(graph, "TAG_")
    assert len(result.auto_shifted) == 1
    positions = {f.cid for f in result.focuses}
    assert positions == {"2", "3"}
    xs = {(f.x, f.y) for f in result.focuses}
    assert len(xs) == 2  # no longer overlapping


def test_build_drawio_focuses_wires_prereqs():
    graph = parse_drawio_graph(TWO_NODE_EDGE)
    result = drawio_to_focus_data(graph, "TAG_")
    focuses = build_drawio_focuses(result)
    by_name = {f.name: f for f in focuses}
    a, b = by_name["TAG_Focus_A"], by_name["TAG_Focus_B"]
    assert b.prereqs == [[a.id]]
    assert a.prereqs == []
    assert a.gfx == "GFX_goal_generic_political_pressure"
    assert a.cost == 10
    assert a.search_filters == "FOCUS_FILTER_POLITICAL"


def test_build_drawio_focuses_does_not_run_on_cancelled_preview():
    # Building the preview data must not itself create Focus objects, so
    # Focus._next stays put until build_drawio_focuses is actually called.
    graph = parse_drawio_graph(TWO_NODE_EDGE)
    before = Focus._next
    drawio_to_focus_data(graph, "TAG_")
    assert Focus._next == before
