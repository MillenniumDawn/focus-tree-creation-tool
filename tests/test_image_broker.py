from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from hoi4cm.mod.graphics_catalog import AssetRef, FileStamp
from hoi4cm.ui.image_broker import ImageBroker, ImageTransform


def _asset(*, generation: int = 1, stamp: int = 1) -> AssetRef:
    return AssetRef("mod", "gfx/icon.png", FileStamp(stamp, stamp, stamp), generation)


def _drain_when_ready(broker: ImageBroker) -> None:
    deadline = time.monotonic() + 2
    while broker.pending and time.monotonic() < deadline:
        broker.drain()
        time.sleep(0.001)
    broker.drain()
    assert not broker.pending


def test_inflight_requests_are_deduplicated_by_stamp_and_transform() -> None:
    calls = []
    gate = threading.Event()

    def decode(path: str, transform: ImageTransform) -> object:
        calls.append((path, transform))
        gate.wait(timeout=2)
        return object()

    with ThreadPoolExecutor(max_workers=2) as executor:
        broker = ImageBroker(
            executor,
            generation=lambda: 1,
            decoder=decode,
            realizer=lambda image: image,
            pillow_available=True,
        )
        results = []
        broker.request(_asset(), "/tmp/icon.png", owner="a", callback=results.append)
        broker.request(_asset(), "/tmp/icon.png", owner="b", callback=results.append)
        gate.set()
        _drain_when_ready(broker)

    assert len(calls) == 1
    assert len(results) == 2


def test_changed_stamp_or_transform_starts_distinct_work() -> None:
    calls = []

    def decode(path: str, transform: ImageTransform) -> object:
        calls.append((path, transform))
        return object()

    with ThreadPoolExecutor(max_workers=2) as executor:
        broker = ImageBroker(
            executor,
            generation=lambda: 1,
            decoder=decode,
            realizer=lambda image: image,
            pillow_available=True,
        )
        broker.request(
            _asset(stamp=1), "/tmp/icon.png", owner=1, callback=lambda _: None
        )
        broker.request(
            _asset(stamp=2), "/tmp/icon.png", owner=2, callback=lambda _: None
        )
        broker.request(
            _asset(stamp=1),
            "/tmp/icon.png",
            transform=ImageTransform((32, 32)),
            owner=3,
            callback=lambda _: None,
        )
        _drain_when_ready(broker)

    assert len(calls) == 3


def test_stale_generation_is_not_realized_or_delivered() -> None:
    generation = 1
    gate = threading.Event()
    realized = []
    delivered = []

    def decode(path: str, transform: ImageTransform) -> object:
        gate.wait(timeout=2)
        return object()

    with ThreadPoolExecutor(max_workers=1) as executor:
        broker = ImageBroker(
            executor,
            generation=lambda: generation,
            decoder=decode,
            realizer=lambda image: realized.append(image),
            pillow_available=True,
        )
        broker.request(_asset(), "/tmp/icon.png", owner=1, callback=delivered.append)
        generation = 2
        gate.set()
        _drain_when_ready(broker)

    assert realized == []
    assert delivered == []


def test_new_generation_does_not_reuse_stale_inflight_decode() -> None:
    generation = 1
    gate = threading.Event()
    decode_count = 0
    old_results = []
    new_results = []

    def decode(path: str, transform: ImageTransform) -> object:
        nonlocal decode_count
        decode_count += 1
        gate.wait(timeout=2)
        return object()

    with ThreadPoolExecutor(max_workers=1) as executor:
        broker = ImageBroker(
            executor,
            generation=lambda: generation,
            decoder=decode,
            realizer=lambda image: image,
            pillow_available=True,
        )
        broker.request(
            _asset(generation=1),
            "/tmp/icon.png",
            owner="old",
            callback=old_results.append,
        )
        generation = 2
        broker.request(
            _asset(generation=2),
            "/tmp/icon.png",
            owner="new",
            callback=new_results.append,
        )
        gate.set()
        _drain_when_ready(broker)

    assert decode_count == 2
    assert old_results == []
    assert len(new_results) == 1


def test_decode_runs_on_worker_and_realization_runs_on_owner_thread() -> None:
    owner_thread = threading.get_ident()
    decode_threads = []
    realize_threads = []

    def decode(path: str, transform: ImageTransform) -> object:
        decode_threads.append(threading.get_ident())
        return object()

    def realize(image: object) -> object:
        realize_threads.append(threading.get_ident())
        return image

    with ThreadPoolExecutor(max_workers=1) as executor:
        broker = ImageBroker(
            executor,
            generation=lambda: 1,
            decoder=decode,
            realizer=realize,
            pillow_available=True,
        )
        broker.request(_asset(), "/tmp/icon.png", owner=1, callback=lambda _: None)
        _drain_when_ready(broker)

    assert decode_threads
    assert all(thread != owner_thread for thread in decode_threads)
    assert realize_threads == [owner_thread]


def test_drain_rejects_non_owner_thread() -> None:
    with ThreadPoolExecutor(max_workers=1) as executor:
        broker = ImageBroker(executor, generation=lambda: 1)
        future = executor.submit(broker.drain)
        with pytest.raises(RuntimeError, match="owner thread"):
            future.result(timeout=2)


def test_cache_and_pins_are_bounded() -> None:
    with ThreadPoolExecutor(max_workers=1) as executor:
        broker = ImageBroker(
            executor,
            generation=lambda: 1,
            decoder=lambda path, transform: object(),
            realizer=lambda image: image,
            pillow_available=True,
            cache_size=2,
            pin_size=1,
        )
        for index in range(3):
            broker.request(
                _asset(stamp=index),
                f"/tmp/{index}.png",
                owner=index,
                callback=lambda _: None,
            )
        _drain_when_ready(broker)

    assert broker.cache_count == 2
    assert broker.pin_count == 1


def test_missing_pillow_does_not_submit_or_realize() -> None:
    decoded = []
    realized = []
    with ThreadPoolExecutor(max_workers=1) as executor:
        broker = ImageBroker(
            executor,
            generation=lambda: 1,
            decoder=lambda path, transform: decoded.append(path),
            realizer=lambda image: realized.append(image),
            pillow_available=False,
        )
        result = broker.request(
            _asset(), "/tmp/icon.png", owner=1, callback=lambda _: None
        )

    assert result is None
    assert decoded == []
    assert realized == []


def test_close_drops_inflight_owner_callback_without_waiting() -> None:
    gate = threading.Event()
    delivered = []

    def decode(path: str, transform: ImageTransform) -> object:
        gate.wait(timeout=2)
        return object()

    executor = ThreadPoolExecutor(max_workers=1)
    broker = ImageBroker(
        executor,
        generation=lambda: 1,
        decoder=decode,
        realizer=lambda image: image,
        pillow_available=True,
    )
    broker.request(_asset(), "/tmp/icon.png", owner="window", callback=delivered.append)

    before = time.monotonic()
    broker.close()
    elapsed = time.monotonic() - before
    gate.set()
    executor.shutdown(wait=True)
    broker.drain()

    assert elapsed < 0.1
    assert delivered == []
    assert not broker.pending
