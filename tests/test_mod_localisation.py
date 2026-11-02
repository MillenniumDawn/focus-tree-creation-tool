import pytest

from hoi4cm.mod import localisation


@pytest.mark.parametrize("root", [None, "", "missing"])
def test_lookup_localisation_returns_empty_for_missing_roots(root):
    assert localisation.lookup_localisation(root, "TST") == ("", "")


def test_lookup_localisation_keeps_first_nonempty_values_and_discovery_order(
    tmp_path, monkeypatch
):
    folder = tmp_path / "localisation" / "english"
    folder.mkdir(parents=True)
    first = folder / "a.yml"
    first.write_text(
        'l_english:\n TST:0 ""\n TST:0 "First title"\n TST:0 "Later title"\n',
        encoding="utf-8",
    )
    second = folder / "b.yml"
    second.write_text(
        'l_english:\n TST:0 "Other title"\n TST_desc:0 "Description"\n',
        encoding="utf-8",
    )
    third = folder / "c.yml"
    third.write_text('l_english:\n TST_desc:0 "Later description"\n', encoding="utf-8")
    reads = []
    read = localisation.read_file_with_encoding

    def tracked(path):
        reads.append(path)
        return read(path)

    monkeypatch.setattr(localisation, "read_file_with_encoding", tracked)

    assert localisation.lookup_localisation(str(tmp_path), "TST") == (
        "First title",
        "Description",
    )
    assert reads == [str(first), str(second)]


def test_lookup_localisation_preserves_raw_values_and_versioned_keys(tmp_path):
    folder = tmp_path / "localisation" / "english"
    folder.mkdir(parents=True)
    (folder / "raw.yml").write_text(
        'l_english:\nTST: "No indentation"\n TST = "Not a matched key"\n'
        ' TST:2 "A \\"quoted\\" title"\n TST_desc:0 "Line\\nnext"\n',
        encoding="utf-8",
    )

    assert localisation.lookup_localisation(str(tmp_path), "TST") == (
        r"A \"quoted\" title",
        r"Line\nnext",
    )


def test_lookup_localisation_keeps_unversioned_colon_keys_unmatched(tmp_path):
    folder = tmp_path / "localisation" / "english"
    folder.mkdir(parents=True)
    (folder / "unversioned.yml").write_text(
        'l_english:\n TST: "Title"\n TST_desc: "Description"\n', encoding="utf-8"
    )

    assert localisation.lookup_localisation(str(tmp_path), "TST") == ("", "")


def test_lookup_localisation_only_reads_the_configured_language(tmp_path):
    for language, title in (("english", "English"), ("french", "Français")):
        folder = tmp_path / "localisation" / language
        folder.mkdir(parents=True)
        (folder / "values.yml").write_text(
            f'l_{language}:\n TST:0 "{title}"\n TST_desc:0 "Description"\n',
            encoding="utf-8",
        )

    assert localisation.lookup_localisation(
        str(tmp_path), "TST", language="french"
    ) == (
        "Français",
        "Description",
    )


@pytest.mark.parametrize(
    "failure",
    [
        None,
        OSError("unreadable"),
        ValueError("invalid"),
        UnicodeDecodeError("utf-8", b"x", 0, 1, "invalid"),
    ],
    ids=["unreadable-result", "os-error", "value-error", "decode-error"],
)
def test_lookup_localisation_skips_unreadable_files(tmp_path, monkeypatch, failure):
    folder = tmp_path / "localisation" / "english"
    folder.mkdir(parents=True)
    bad = folder / "a.yml"
    bad.touch()
    good = folder / "b.yml"
    good.write_text('l_english:\n TST:0 "Title"\n', encoding="utf-8")
    read = localisation.read_file_with_encoding

    def read_with_failure(path):
        if path == str(bad):
            if failure is not None:
                raise failure
            return None, None
        return read(path)

    monkeypatch.setattr(localisation, "read_file_with_encoding", read_with_failure)

    assert localisation.lookup_localisation(str(tmp_path), "TST") == ("Title", "")
