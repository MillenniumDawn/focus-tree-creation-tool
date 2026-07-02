"""Tests for hoi4cm.core.safe_xml — bounded inflate + hardened XML parse."""

import zlib

import pytest

from hoi4cm.core import safe_xml


def _raw_deflate(data):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def test_bounded_inflate_roundtrips_small():
    payload = _raw_deflate(b"<mxGraphModel><root/></mxGraphModel>")
    assert safe_xml.bounded_inflate(payload) == b"<mxGraphModel><root/></mxGraphModel>"


def test_bounded_inflate_rejects_bomb():
    payload = _raw_deflate(b"A" * 200_000)
    with pytest.raises(ValueError):
        safe_xml.bounded_inflate(payload, max_bytes=1024)


def test_safe_fromstring_parses_plain_xml():
    root = safe_xml.safe_fromstring("<mxGraphModel><root id='0'/></mxGraphModel>")
    assert root.tag == "mxGraphModel"
    assert root.find("root").get("id") == "0"


def test_safe_fromstring_rejects_billion_laughs():
    bomb = (
        "<?xml version='1.0'?>"
        "<!DOCTYPE lolz [<!ENTITY lol 'lol'>"
        "<!ENTITY lol2 '&lol;&lol;&lol;&lol;'>]>"
        "<lolz>&lol2;</lolz>"
    )
    with pytest.raises(ValueError):
        safe_xml.safe_fromstring(bomb)


def test_safe_fromstring_rejects_any_doctype():
    doc = "<!DOCTYPE note SYSTEM 'note.dtd'><note/>"
    with pytest.raises(ValueError):
        safe_xml.safe_fromstring(doc)


def test_safe_fromstring_rejects_oversize_input():
    with pytest.raises(ValueError):
        safe_xml.safe_fromstring("<a/>" + " " * 100, max_bytes=8)
