import hashlib

from hoi4cm.data import EFFECT_DEFS
from hoi4cm.script.effects import render_effect


def test_all_defined_effect_default_renderings_are_unchanged():
    rendered = []
    for effect_type in sorted(EFFECT_DEFS):
        fields = {
            field[0]: field[2] for field in EFFECT_DEFS[effect_type].get("fields", [])
        }
        rendered.append(
            f"{effect_type}\0{render_effect({'type': effect_type, 'fields': fields})}"
        )

    digest = hashlib.sha256("\0".join(rendered).encode()).hexdigest()
    assert len(rendered) == 641
    assert digest == "15b0df4d0cd418b8892e8b893c4b4d3d479e1f337d60fb46540b96009801d074"


def test_raw_effect_preserves_lines_with_completion_reward_indent():
    effect = {
        "type": "_raw_block",
        "fields": {"raw": "if = {\n\tlimit = { always = yes }\n\teffect = yes\n}"},
    }

    assert render_effect(effect) == (
        "\t\t\tif = {\n"
        "\t\t\t\tlimit = { always = yes }\n"
        "\t\t\t\teffect = yes\n"
        "\t\t\t}"
    )


def test_unknown_effect_uses_generic_fallback():
    effect = {"type": "custom_unknown", "fields": {"target": "ENG", "value": 2}}

    assert render_effect(effect) == (
        "\t\t\tcustom_unknown = {\n"
        "\t\t\t\ttarget = ENG\n"
        "\t\t\t\tvalue = 2\n"
        "\t\t\t}"
    )
