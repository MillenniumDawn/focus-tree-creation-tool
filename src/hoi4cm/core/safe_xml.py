"""Bounded decompression + hardened XML parsing for untrusted Draw.io files.

A ``.drawio`` file is downloaded/shared, so its embedded, zlib-compressed XML
is untrusted. Two classic DoS vectors are closed here: a decompression bomb
(tiny input inflating to gigabytes) and XML entity expansion (billion laughs).
Stdlib only — no defusedxml dependency.
"""

import xml.etree.ElementTree as ET
import zlib

MAX_XML_BYTES = 64 * 1024 * 1024


def bounded_inflate(data, wbits=-15, max_bytes=MAX_XML_BYTES):
    """Inflate *data*, refusing output larger than *max_bytes*.

    Returns the decompressed ``bytes``. Raises ``ValueError`` if the stream
    would exceed the cap.
    """
    dobj = zlib.decompressobj(wbits)
    out = dobj.decompress(data, max_bytes)
    if dobj.unconsumed_tail:
        raise ValueError("decompressed data exceeds size limit")
    out += dobj.flush()
    if len(out) > max_bytes:
        raise ValueError("decompressed data exceeds size limit")
    return out


def _reject_dtd(xml_str):
    # A DOCTYPE is the only way to declare internal ENTITY definitions, so
    # refusing it blocks billion-laughs / quadratic-blowup entity expansion.
    # ``ET.XMLParser`` no longer exposes its expat handlers across Python
    # versions, so scan the markup directly. Both tokens are case-sensitive
    # per the XML spec and only appear as literal markup (content escapes them
    # as ``&lt;!...``), so a substring check is reliable.
    blob = (
        xml_str
        if isinstance(xml_str, bytes)
        else xml_str.encode("utf-8", errors="ignore")
    )
    if b"<!DOCTYPE" in blob or b"<!ENTITY" in blob:
        raise ValueError("XML DOCTYPE/ENTITY declarations are not allowed")


def safe_fromstring(xml_str, max_bytes=MAX_XML_BYTES):
    """Parse *xml_str* like ``ET.fromstring`` but reject DOCTYPE/entities and
    oversize input. Raises ``ValueError`` on either."""
    if isinstance(xml_str, bytes):
        size = len(xml_str)
    else:
        size = len(xml_str.encode("utf-8", errors="ignore"))
    if size > max_bytes:
        raise ValueError("XML input exceeds size limit")
    _reject_dtd(xml_str)
    return ET.fromstring(xml_str)
