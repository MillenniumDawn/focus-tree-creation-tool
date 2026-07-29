"""Draw.io diagram import — mxGraph XML in, HOI4 focus data out.

Pure functions: no tkinter, no file I/O. The caller (the Tk shell in
``hoi4_content_maker.py``) reads the file, decompresses/parses it through
:mod:`hoi4cm.core.safe_xml`'s hardened helpers via :func:`parse_drawio_graph`,
shows the user a setup dialog to collect the country tag/prefix, calls
:func:`drawio_to_focus_data` to snap the shapes onto the HOI4 grid for
preview, and only once the user confirms the import calls
:func:`build_drawio_focuses` to turn that into real
:class:`~hoi4cm.models.Focus` objects (deferred that far because Focus IDs
come from a process-global counter that shouldn't advance on a cancelled
import).
"""

from __future__ import annotations

import base64
import re
import urllib.parse
from dataclasses import dataclass

from hoi4cm.core.safe_xml import bounded_inflate, safe_fromstring
from hoi4cm.models import Focus


class EmptyDrawioGraphError(ValueError):
    """Raised when a draw.io diagram has no recognizable focus shapes."""


@dataclass
class DrawioVertex:
    """One shape from the diagram, in diagram pixel space."""

    cid: str
    label: str
    x: float
    y: float


@dataclass
class DrawioGraph:
    """Vertices + prerequisite edges extracted from an mxGraph document."""

    vertices: dict  # cid -> DrawioVertex
    edges: list  # [(source_cid, target_cid), ...]


@dataclass
class DrawioFocus:
    """One shape mapped onto the HOI4 grid, with the tag prefix applied."""

    cid: str
    label: str
    x: int
    y: int


@dataclass
class DrawioResult:
    """Output of :func:`drawio_to_focus_data`, ready for preview or commit."""

    focuses: list  # [DrawioFocus, ...], sorted in visual (row, then col) order
    edges: list  # [(source_cid, target_cid), ...], same as the parsed graph
    auto_shifted: list  # [(label, orig_x, orig_y, new_x, new_y), ...]


def decompress_drawio(b64_text):
    """Undo draw.io's page encoding: base64 -> raw deflate -> URL-decode."""
    data = base64.b64decode(b64_text)
    return urllib.parse.unquote(bounded_inflate(data).decode("utf-8"))


def _get_graph_root(xml_text):
    """Return the ``mxGraphModel`` element, decompressing a page if needed.

    Handles both a bare ``mxGraphModel`` document and the multi-page
    ``mxfile``/``diagram`` wrapper draw.io normally saves, where each
    ``diagram`` holds its model either inline or base64+deflate compressed.
    Only the first usable page is returned, matching the original behavior.
    """
    root = safe_fromstring(xml_text)
    if root.tag == "mxGraphModel":
        return root
    for diag in root.iter("diagram"):
        text = (diag.text or "").strip()
        if not text:
            if diag.find(".//mxCell") is not None:
                return diag
            continue
        try:
            return safe_fromstring(decompress_drawio(text))
        except Exception:
            pass
        try:
            return safe_fromstring(text)
        except Exception:
            pass
    return root


def clean_label(raw):
    """Strip a draw.io shape label down to an HOI4-safe identifier fragment."""
    s = re.sub(r"<[^>]+>", "", raw or "")
    for ent, ch in [
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&nbsp;", " "),
        ("&#xa;", ""),
    ]:
        s = s.replace(ent, ch)
    s = s.strip()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_]", "", s)
    return s


def _read_geometry(geo):
    try:
        x = float(geo.get("x", 0) or 0)
        y = float(geo.get("y", 0) or 0)
    except Exception:
        x = y = 0
    return x, y


def parse_drawio_graph(xml_text):
    """Parse mxGraph XML text into vertices + prerequisite edges.

    Raises ``xml.etree.ElementTree.ParseError`` / ``ValueError`` on malformed,
    oversized, or DOCTYPE-bearing XML (via ``safe_fromstring``/
    ``bounded_inflate``), and :class:`EmptyDrawioGraphError` when no vertex
    shapes are found.
    """
    graph_root = _get_graph_root(xml_text)
    cells = graph_root.findall(".//mxCell")

    vertices = {}
    for c in cells:
        cid = c.get("id", "")
        if c.get("vertex") != "1" or cid in ("0", "1", ""):
            continue
        geo = c.find("mxGeometry")
        if geo is None:
            continue
        label = clean_label(c.get("value", "")) or f"focus_{cid}"
        x, y = _read_geometry(geo)
        vertices[cid] = DrawioVertex(cid=cid, label=label, x=x, y=y)

    # UserObject / object wrappers carry the label outside the inner mxCell,
    # which the loop above will already have picked up with a placeholder
    # label — overwrite it with the real one.
    for obj in graph_root.findall(".//UserObject") + graph_root.findall(".//object"):
        inner = obj.find("mxCell")
        if inner is None or inner.get("vertex") != "1":
            continue
        cid = obj.get("id") or inner.get("id", "")
        if not cid or cid in ("0", "1"):
            continue
        geo = inner.find("mxGeometry")
        if geo is None:
            continue
        label = (
            clean_label(obj.get("label") or obj.get("value") or obj.get("name") or "")
            or f"focus_{cid}"
        )
        x, y = _read_geometry(geo)
        vertices[cid] = DrawioVertex(cid=cid, label=label, x=x, y=y)

    if not vertices:
        raise EmptyDrawioGraphError("No shapes found in the diagram.")

    edges = []
    for c in cells:
        if c.get("edge") != "1":
            continue
        src = c.get("source", "")
        tgt = c.get("target", "")
        if src in vertices and tgt in vertices:
            edges.append((src, tgt))

    return DrawioGraph(vertices=vertices, edges=edges)


def _cluster_axis(values, tolerance_ratio=0.55):
    """Group pixel coords into discrete slots using centroid clustering.

    ``tolerance_ratio`` is the fraction of the median gap used as the merge
    threshold. Returns a ``{rounded_value: cluster_index}`` mapping.
    """
    vals = sorted(set(round(v) for v in values))
    if not vals:
        return {}
    gaps = [b - a for a, b in zip(vals, vals[1:], strict=False) if b - a > 2]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 80
    tol = max(10, median_gap * tolerance_ratio)
    clusters = []
    for v in vals:
        if clusters and v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    mapping = {}
    for idx, cluster in enumerate(clusters):
        for v in cluster:
            mapping[v] = idx
    return mapping


def _snap(val, mapping):
    """Find the nearest key in ``mapping`` to ``val``."""
    rounded = round(val)
    if rounded in mapping:
        return mapping[rounded]
    return mapping[min(mapping.keys(), key=lambda k: abs(k - val))]


def _assign_grid_positions(vertices):
    """Cluster vertex pixel coordinates into a compact HOI4 grid.

    Clusters into rows/columns by proximity, then assigns HOI4 grid slots
    (even columns, integer rows), nudging right and then wrapping to the next
    row to resolve collisions. Returns ``(grid_positions, auto_shifted)``
    where ``grid_positions`` is ``{cid: (x, y)}`` and ``auto_shifted`` lists
    ``(label, orig_x, orig_y, new_x, new_y)`` for every focus that was moved.
    """
    all_px = [v.x for v in vertices.values()]
    all_py = [v.y for v in vertices.values()]

    x_cluster = _cluster_axis(all_px, tolerance_ratio=0.60)
    y_cluster = _cluster_axis(all_py, tolerance_ratio=0.60)

    raw_grid = {}
    for cid, v in vertices.items():
        col = _snap(v.x, x_cluster)
        row = _snap(v.y, y_cluster)
        raw_grid[cid] = (col, row)

    used = {}  # (gx, gy) -> cid
    grid_positions = {}
    auto_shifted = []

    def _find_free(gx_start, gy, max_right_search=30):
        gx = gx_start
        for _ in range(max_right_search):
            if (gx, gy) not in used:
                return gx, gy
            gx += 2
        gy_try = gy + 1
        gx_try = gx_start
        while (gx_try, gy_try) in used:
            gx_try += 2
        return gx_try, gy_try

    for cid in sorted(raw_grid.keys(), key=lambda c: (raw_grid[c][1], raw_grid[c][0])):
        col_idx, row_idx = raw_grid[cid]
        gx_orig = col_idx * 2  # HOI4 uses even columns
        gy_orig = row_idx

        if (gx_orig, gy_orig) not in used:
            gx, gy = gx_orig, gy_orig
        else:
            gx, gy = _find_free(gx_orig, gy_orig)
            auto_shifted.append((vertices[cid].label, gx_orig, gy_orig, gx, gy))

        used[(gx, gy)] = cid
        grid_positions[cid] = (gx, gy)

    return grid_positions, auto_shifted


def drawio_to_focus_data(graph, prefix):
    """Apply the tag ``prefix`` and snap ``graph``'s vertices onto the HOI4 grid.

    Does not mutate ``graph``. Returns a :class:`DrawioResult` whose
    ``focuses`` are sorted in visual (row, then column) reading order, which
    is also the order the code/list preview panes and the eventual
    :func:`build_drawio_focuses` call use.
    """
    prefixed = {}
    for cid, v in graph.vertices.items():
        label = v.label
        if not label.upper().startswith(prefix.upper()):
            label = prefix + label
        prefixed[cid] = DrawioVertex(cid=cid, label=label, x=v.x, y=v.y)

    grid_positions, auto_shifted = _assign_grid_positions(prefixed)

    sorted_cids = sorted(
        prefixed, key=lambda c: (grid_positions[c][1], grid_positions[c][0])
    )
    focuses = [
        DrawioFocus(
            cid=cid,
            label=prefixed[cid].label,
            x=grid_positions[cid][0],
            y=grid_positions[cid][1],
        )
        for cid in sorted_cids
    ]
    return DrawioResult(
        focuses=focuses, edges=list(graph.edges), auto_shifted=auto_shifted
    )


def build_drawio_focuses(result):
    """Turn a :class:`DrawioResult` into real :class:`Focus` objects.

    Only call this once the user has confirmed the import — ``Focus`` IDs
    come from a process-global counter, so building them speculatively for a
    preview would burn IDs on a cancelled import.
    """
    cid_to_fid = {}
    new_focuses = []
    for df in result.focuses:
        f = Focus(df.x, df.y)
        f.name = df.label
        new_focuses.append(f)
        cid_to_fid[df.cid] = f.id

    by_id = {f.id: f for f in new_focuses}
    for src_cid, tgt_cid in result.edges:
        if src_cid in cid_to_fid and tgt_cid in cid_to_fid:
            by_id[cid_to_fid[tgt_cid]].prereqs.append([cid_to_fid[src_cid]])

    return new_focuses
