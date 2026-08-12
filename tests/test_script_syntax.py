from hoi4cm.focus_tree.parse import block_to_str
from hoi4cm.mod.context import ModContext
from hoi4cm.script import dict_to_raw
from hoi4cm.script.syntax import (
    extract_block,
    extract_named_block,
    find_blocks,
    match_brace,
    parse_block,
    parse_script,
    serialize_block,
    strip_comments,
    tokenize,
)


def test_tokenize_ignores_comments_only_outside_quotes():
    source = 'name = "value # { quoted } text" # } ignored\nnext = yes'

    assert tokenize(source) == [
        "name",
        "=",
        "value # { quoted } text",
        "next",
        "=",
        "yes",
    ]
    assert strip_comments(source) == 'name = "value # { quoted } text" \nnext = yes'


def test_trailing_backslash_quote_does_not_swallow_closing_quote():
    source = 'focus = { icon = "gfx\\interface\\" cost = 5 }\nnext = yes'

    assert tokenize(source) == [
        "focus",
        "=",
        "{",
        "icon",
        "=",
        "gfx\\interface\\",
        "cost",
        "=",
        "5",
        "}",
        "next",
        "=",
        "yes",
    ]
    assert strip_comments(source) == source

    open_index = source.index("{")
    close_index = match_brace(source, open_index)
    assert source[close_index:] == "}\nnext = yes"

    blocks = find_blocks(source)
    assert [name for name, _, _ in blocks] == ["focus"]
    assert blocks[0][2] == 'focus = { icon = "gfx\\interface\\" cost = 5 }'


def test_unterminated_quote_runs_to_the_end_of_its_own_line():
    """A missing closing quote must not leak into the following line.

    ``strip_comments`` works a line at a time, so an unterminated string
    protects the rest of *its* line from comment stripping and nothing more.
    """
    source = 'a = "open # not a comment\nb = yes # a comment\nc = "x"'

    assert strip_comments(source) == 'a = "open # not a comment\nb = yes \nc = "x"'
    # tokenize has no line concept, so there the string runs to the next quote
    # and the last quote opens an unterminated (empty) one.
    assert tokenize(source) == [
        "a",
        "=",
        "open # not a comment\nb = yes # a comment\nc = ",
        "x",
        "",
    ]


def test_comment_only_line_survives_as_an_empty_line():
    """Raw-block dedenting counts lines, so a stripped comment leaves one."""
    source = "focus = {\n\t# note\n\tid = a\n}"

    assert strip_comments(source) == "focus = {\n\t\n\tid = a\n}"


def test_strip_comments_normalizes_every_line_break_form():
    # CRLF and a lone CR both collapse to "\n", and a trailing line break is
    # dropped — long-standing splitlines()/join() behavior the raw-block
    # dedenting downstream is written against.
    assert strip_comments("a # x\r\nb # y\rc # z\n") == "a \nb \nc "
    assert strip_comments("a # x\n") == "a "
    assert strip_comments("a # x") == "a "


def test_tokenize_handles_empty_and_unterminated_quoted_values():
    assert tokenize('a = "" b = "') == ["a", "=", "", "b", "=", ""]
    assert tokenize("# only a comment") == []
    assert tokenize("") == []


def test_nested_braces_inside_strings_do_not_shift_brace_matching():
    source = 'outer = { inner = "{{{" deeper = { x = "}}}" } }'

    open_index = source.index("{")
    assert match_brace(source, open_index) == len(source) - 1
    blocks = find_blocks(source)
    assert [name for name, _, _ in blocks] == ["outer"]
    assert extract_named_block(source, "deeper") == ' x = "}}}" '


def test_match_and_extract_block_ignore_braces_in_strings_and_comments():
    source = '{ text = "}" # }\n nested = { value = "{" } } trailing'

    close_index = match_brace(source, 0)

    assert source[close_index:] == "} trailing"
    assert extract_block(source) == (source[1:close_index], close_index)


def test_extract_unbalanced_block_preserves_tolerant_remainder():
    assert extract_block("{ value = yes") == (" value = yes", 12)
    assert match_brace("{ value = yes", 0) == 13


def test_parse_script_preserves_duplicate_keys_and_bare_values():
    parsed = parse_script(
        'item = first item = { nested = yes } values = { one "two words" }'
    )

    assert parsed == {
        "item": ["first", {"nested": "yes"}],
        "values": {"_values": ["one", "two words"]},
    }


def test_parse_block_tolerates_missing_value():
    assert parse_block(["{", "good", "=", "yes", "broken", "="], 0) == (
        {"good": "yes"},
        7,
    )


def test_find_blocks_preserves_raw_source_and_skips_false_blocks():
    source = (
        "# fake = { nope = yes }\n"
        'first = { text = "} # not a comment" nested = { x = 1 } }\n\n'
        "second = { y = 2 }"
    )

    blocks = find_blocks(source)

    assert [name for name, _, _ in blocks] == ["first", "second"]
    assert blocks[0][2] == (
        '\nfirst = { text = "} # not a comment" nested = { x = 1 } }'
    )
    assert blocks[1][2] == "\n\nsecond = { y = 2 }"
    assert extract_named_block(source, "nested") == " x = 1 "
    assert extract_named_block("notnested = { x = 1 }", "nested") is None


def test_recursive_serializer_supports_bare_values_and_duplicate_keys():
    parsed = {
        "item": ["first", {"enabled": True}],
        "values": {"_values": ["one", "two words"]},
    }

    assert serialize_block(parsed, indent="", include_bare_values=True) == (
        "item = first\n"
        "item = {\n\tenabled = yes\n}\n"
        "values = {\n\tone\n\ttwo words\n}"
    )


def test_compatibility_consumers_share_parser_and_serializer_semantics():
    source = 'root = { value = one value = two text = "# { }" }'
    tokens = tokenize(source)

    assert ModContext._tokenize(source) == tokens
    assert ModContext._parse_block(["{", *tokens, "}"], 0)[0] == parse_script(source)
    assert ModContext._parse_text(source) == parse_script(source)

    value = {"enabled": True, "nested": {"item": ["a", "b"]}}
    assert dict_to_raw(value) == serialize_block(value)
    assert block_to_str(value) == serialize_block(
        value, indent="\t", strip_strings=True
    )
