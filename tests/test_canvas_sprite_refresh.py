"""Write-time invalidation of visible canvas icons (#394).

``_draw_focus`` skips a card whose state key is unchanged, so a rewritten
sprite never reaches the image broker unless the write clears the card's
``draw_key``. These tests drive the real ``App.note_mod_file_written`` against a
real catalog and broker, with a fake decoder standing in for Pillow.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
from ui_fakes import AppFake

import hoi4_content_maker as app_module
from hoi4cm.mod import scan_cache as scan_cache_mod
from hoi4cm.mod.graphics_catalog import AssetRef, FileStamp
from hoi4cm.models import Focus
from hoi4cm.ui.canvas_renderer import FocusCanvasBundle
from hoi4cm.ui.canvas_scheduler import RedrawChannel
from hoi4cm.ui.image_broker import ImageBroker, ImageTransform

_REMAP_GFX = 'spriteType = {{ name = "GFX_remap" texturefile = "{texture}" }}\n'
_ALPHA = "gfx/interface/goals/alpha.dds"
_BETA = "gfx/interface/goals/beta.dds"


def _pump(broker: ImageBroker, done: Callable[[], bool] | None = None) -> None:
    """Drain the broker on this thread until *done* (default: nothing pending)."""
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        broker.drain()
        if done() if done is not None else not broker.pending:
            return
        time.sleep(0.001)
    pytest.fail("timed out waiting for the image broker")


class _Decoder:
    """Return the file's bytes as the decoded image, optionally held open."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.hold: dict[str, threading.Event] = {}
        self.started = threading.Event()

    def __call__(self, path: str, transform: ImageTransform) -> object:
        data = Path(path).read_bytes()
        name = Path(path).name
        self.calls.append(name)
        gate = self.hold.pop(name, None)
        if gate is not None:
            self.started.set()
            gate.wait(timeout=2)
        return data


class _Canvas:
    def __init__(self, root: Path, executor: ThreadPoolExecutor) -> None:
        self.root = root
        self.decoder = _Decoder()
        self.fake = AppFake(
            [
                _focus(1, "GFX_focus_alpha"),
                _focus(2, "GFX_remap"),
                _focus(3, "GFX_focus_other"),
            ],
            cv=Mock(),
        )
        self.fake.index.scan(str(root))
        catalog = self.fake.index.graphics_catalog
        self.broker = ImageBroker(
            executor,
            generation=lambda: catalog.generation,
            decoder=self.decoder,
            realizer=lambda image: image,
            pillow_available=True,
            on_dropped=self.fake._on_broker_dropped,
        )
        self.fake._image_broker = self.broker
        self.fake.__dict__["_redraw"] = Mock()
        self.fake.__dict__["_visible_rect"] = Mock(return_value=None)
        self.fake.note_mod_file_written = app_module.App.note_mod_file_written.__get__(
            self.fake
        )

    def draw(self) -> None:
        for focus in self.fake.focuses.values():
            self.fake._draw_focus(focus)

    def bundle(self, focus_id: int) -> FocusCanvasBundle:
        return self.fake._focus_bundles[focus_id]

    def settle(self, done: Callable[[], bool] | None = None) -> None:
        _pump(self.broker, done)

    def write(self, relative: str, content: bytes | str) -> str:
        path = self.root / relative
        if isinstance(content, str):
            path.write_text(content)
        else:
            path.write_bytes(content)
        return str(path)

    def redraws(self) -> int:
        return self.fake.mock("_redraw").call_count


def _focus(focus_id: int, gfx: str) -> Focus:
    focus = Focus(id=focus_id)
    focus.gfx = gfx
    return focus


@pytest.fixture
def canvas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Canvas]:
    monkeypatch.setattr(scan_cache_mod, "STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "mod"
    (root / "gfx" / "interface" / "goals").mkdir(parents=True)
    (root / "interface").mkdir()
    for name in ("alpha", "beta", "other"):
        (root / "gfx" / "interface" / "goals" / f"{name}.dds").write_bytes(
            f"{name}-v1".encode()
        )
    (root / "interface" / "remap.gfx").write_text(_REMAP_GFX.format(texture=_ALPHA))
    with ThreadPoolExecutor(max_workers=2) as executor:
        yield _Canvas(root, executor)


def test_same_name_overwrite_refreshes_visible_icon(canvas: _Canvas) -> None:
    canvas.draw()
    canvas.settle()
    assert canvas.bundle(1).image == b"alpha-v1"

    path = canvas.write(_ALPHA, b"alpha-v2-longer")
    canvas.fake.note_mod_file_written(path)
    assert canvas.redraws() == 1

    canvas.draw()
    canvas.settle()
    assert canvas.bundle(1).image == b"alpha-v2-longer"


def test_same_name_texture_remap_refreshes_visible_icon(canvas: _Canvas) -> None:
    canvas.draw()
    canvas.settle()
    assert canvas.bundle(2).image == b"alpha-v1"

    path = canvas.write("interface/remap.gfx", _REMAP_GFX.format(texture=_BETA))
    canvas.fake.note_mod_file_written(path)
    assert canvas.redraws() == 1

    canvas.draw()
    canvas.settle()
    assert canvas.bundle(2).image == b"beta-v1"


def test_write_evicts_the_cached_path_of_each_changed_sprite(
    canvas: _Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = Mock(wraps=canvas.broker.evict_paths)
    monkeypatch.setattr(canvas.broker, "evict_paths", spy)

    canvas.fake.note_mod_file_written(canvas.write(_ALPHA, b"alpha-v2-longer"))

    spy.assert_called_once()
    assert {Path(path).name for path in spy.call_args.args[0]} == {"alpha.dds"}


def test_unrelated_warm_icon_is_not_redrawn_or_redecoded(canvas: _Canvas) -> None:
    canvas.draw()
    canvas.settle()
    unrelated = canvas.bundle(3)
    warm_key = unrelated.draw_key
    assert warm_key is not None

    canvas.fake.note_mod_file_written(canvas.write(_ALPHA, b"alpha-v2-longer"))
    canvas.draw()
    canvas.settle()

    assert unrelated.draw_key is warm_key
    assert unrelated.image == b"other-v1"
    assert canvas.decoder.calls.count("other.dds") == 1


def test_write_that_changes_no_sprite_requests_no_redraw(canvas: _Canvas) -> None:
    canvas.draw()
    canvas.settle()

    canvas.fake.note_mod_file_written(canvas.write("common_note.txt", "x = 1\n"))

    assert canvas.redraws() == 0
    assert canvas.bundle(1).draw_key is not None


def test_stale_completion_after_the_write_is_not_delivered(canvas: _Canvas) -> None:
    gate = threading.Event()
    canvas.decoder.hold["alpha.dds"] = gate
    canvas.draw()  # alpha-v1 decode starts and is held open
    assert canvas.decoder.started.wait(timeout=2)

    canvas.fake.note_mod_file_written(canvas.write(_ALPHA, b"alpha-v2-longer"))
    gate.set()
    canvas.settle()
    assert canvas.bundle(1).image is None  # the old decode was discarded

    canvas.draw()
    canvas.settle()
    assert canvas.bundle(1).image == b"alpha-v2-longer"


def test_stale_completion_cannot_replace_the_refreshed_icon(canvas: _Canvas) -> None:
    gate = threading.Event()
    canvas.decoder.hold["alpha.dds"] = gate
    canvas.draw()  # alpha-v1 decode starts and is held open
    assert canvas.decoder.started.wait(timeout=2)

    canvas.fake.note_mod_file_written(canvas.write(_ALPHA, b"alpha-v2-longer"))
    canvas.draw()  # refreshed request runs on the second worker
    canvas.settle(lambda: canvas.bundle(1).image == b"alpha-v2-longer")

    gate.set()  # the stale decode now finishes after the refreshed one
    canvas.settle()
    assert canvas.bundle(1).image == b"alpha-v2-longer"


def test_dropped_pending_card_re_requests_on_the_next_frame(canvas: _Canvas) -> None:
    """An unrelated successful write must not strand a pending card."""
    canvas.fake._draw_focus(canvas.fake.focuses[3])
    canvas.settle()
    warm_key = canvas.bundle(3).draw_key
    assert canvas.bundle(3).image == b"other-v1"

    gate = threading.Event()
    canvas.decoder.hold["alpha.dds"] = gate
    canvas.draw()  # the alpha decode starts and is held open
    assert canvas.decoder.started.wait(timeout=2)

    canvas.fake.note_mod_file_written(canvas.write(_BETA, b"beta-v2-longer"))
    assert canvas.redraws() == 0  # no visible sprite was touched
    gate.set()
    canvas.settle()
    assert canvas.bundle(1).image is None  # stale result suppressed
    assert canvas.bundle(1).draw_key is None
    canvas.fake.mock("_redraw").assert_any_call(
        RedrawChannel.VIEW, reason="image-dropped"
    )

    canvas.draw()  # the retry frame
    canvas.settle()
    assert canvas.bundle(1).image == b"alpha-v1"
    assert canvas.decoder.calls.count("alpha.dds") == 2
    assert canvas.bundle(3).draw_key is warm_key
    assert canvas.bundle(3).image == b"other-v1"
    assert canvas.decoder.calls.count("other.dds") == 1

    # Delivered-image control: later frames neither redraw nor decode again.
    redraws, decodes = canvas.redraws(), canvas.decoder.calls.count("alpha.dds")
    canvas.draw()
    canvas.settle()
    assert canvas.redraws() == redraws
    assert canvas.decoder.calls.count("alpha.dds") == decodes


def test_replaced_gfx_skips_the_dropped_sprite_retry(canvas: _Canvas) -> None:
    """A card whose gfx changed while its decode was dropped retries the new gfx."""
    canvas.fake.focuses.delete_many([1])
    gate = threading.Event()
    canvas.decoder.hold["alpha.dds"] = gate
    canvas.draw()
    assert canvas.decoder.started.wait(timeout=2)

    canvas.fake.note_mod_file_written(canvas.write(_BETA, b"beta-v2-longer"))
    gate.set()
    canvas.settle()
    assert canvas.bundle(2).draw_key is None

    canvas.fake.focuses[2].gfx = "GFX_focus_other"
    canvas.draw()
    canvas.settle()
    assert canvas.bundle(2).image == b"other-v1"
    assert canvas.decoder.calls.count("alpha.dds") == 1


def test_invalidation_clears_only_matching_full_detail_bundles() -> None:
    fake = AppFake(
        [_focus(1, "GFX_a"), _focus(2, "GFX_b"), _focus(3, "GFX_a")],
    )
    fake._focus_bundles = {
        1: FocusCanvasBundle((), "full", draw_key="k1"),
        2: FocusCanvasBundle((), "full", draw_key="k2"),
        3: FocusCanvasBundle((), "compact", draw_key="k3"),
    }

    fake._invalidate_canvas_sprites({"GFX_a"})

    assert {fid: bundle.draw_key for fid, bundle in fake._focus_bundles.items()} == {
        1: None,
        2: "k2",
        3: "k3",
    }
    fake.mock("_redraw").assert_called_once()


@pytest.mark.parametrize("names", [set(), {"GFX_unused"}])
def test_invalidation_without_a_visible_match_does_not_redraw(names: set[str]) -> None:
    fake = AppFake([_focus(1, "GFX_a")])
    fake._focus_bundles = {1: FocusCanvasBundle((), "full", draw_key="k1")}

    fake._invalidate_canvas_sprites(names)

    assert fake._focus_bundles[1].draw_key == "k1"
    fake.mock("_redraw").assert_not_called()


def test_evict_paths_drops_only_that_path_even_with_an_unchanged_stamp(
    tmp_path: Path,
) -> None:
    decodes: list[str] = []

    def decode(path: str, transform: ImageTransform) -> object:
        decodes.append(Path(path).name)
        return object()

    asset = AssetRef("mod", "icon.png", FileStamp(1, 1, 1), 1)
    first, second = str(tmp_path / "first.png"), str(tmp_path / "second.png")
    with ThreadPoolExecutor(max_workers=1) as executor:
        broker = ImageBroker(
            executor,
            generation=lambda: 1,
            decoder=decode,
            realizer=lambda image: image,
            pillow_available=True,
        )
        for owner, path in enumerate((first, second)):
            broker.request(asset, path, owner=owner, callback=lambda _: None)
        _pump(broker)
        assert broker.cache_count == 2

        broker.evict_paths([first])

        assert broker.cache_count == 1
        assert (
            broker.request(asset, second, owner=2, callback=lambda _: None) is not None
        )
        assert broker.request(asset, first, owner=3, callback=lambda _: None) is None
        _pump(broker)

    assert decodes == ["first.png", "second.png", "first.png"]
