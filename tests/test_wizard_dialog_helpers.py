import pytest

from hoi4cm.wizards._shared import format_save_summary


@pytest.mark.parametrize(
    ("saved", "warnings", "errs", "expected"),
    [
        (["a.txt"], [], [], "Saved:\na.txt"),
        (["a.txt", "b.txt"], [], [], "Saved:\na.txt\nb.txt"),
        (
            ["a.txt"],
            ["no new keys"],
            ["boom"],
            "Saved:\na.txt\n\nNotes:\nno new keys\n\nErrors:\nboom",
        ),
        ([], ["no new keys"], [], "Notes:\nno new keys"),
        ([], [], ["boom"], "Errors:\nboom"),
        (["a.txt"], [], ["boom"], "Saved:\na.txt\n\nErrors:\nboom"),
        ([], [], [], "Nothing to save."),
    ],
)
def test_format_save_summary(saved, warnings, errs, expected):
    assert format_save_summary(saved, warnings, errs) == expected


def test_format_save_summary_accepts_any_sequence():
    assert format_save_summary(("a.txt",), (), ("boom",)) == (
        "Saved:\na.txt\n\nErrors:\nboom"
    )
