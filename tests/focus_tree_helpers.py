"""Rendering and structural comparisons shared by focus-tree export tests."""


def raw_block_renderer(eff):
    """Mirror the monolith's _raw_block effect rendering (3-tab base indent)."""
    if eff.get("type") != "_raw_block":
        return ""
    raw = eff.get("fields", {}).get("raw", "").strip()
    return "\n".join(f"\t\t\t{ln}" for ln in raw.splitlines()) if raw else ""


def focus_summary(focuses):
    by_id = {f.id: f.name for f in focuses}
    return [
        (
            f.name,
            f.gfx,
            f.cost,
            f.x,
            f.y,
            getattr(f, "relative_position_id", None),
            tuple(tuple(by_id.get(i, i) for i in grp) for grp in f.prereqs),
            tuple(by_id.get(i, i) for i in f.mutex),
            tuple((o["x"], o["y"]) for o in f.offsets),
            f.ai_will_do,
            f.search_filters,
        )
        for f in focuses
    ]
