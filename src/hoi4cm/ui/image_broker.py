from __future__ import annotations

import os
import queue
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from concurrent.futures import Executor, Future
from dataclasses import dataclass

from hoi4cm.core.image import PIL_OK, PILImage, PILImageTk
from hoi4cm.core.logger import get_logger
from hoi4cm.mod.graphics_catalog import AssetRef, FileStamp

log = get_logger("image_broker")


@dataclass(frozen=True)
class ImageTransform:
    size: tuple[int, int] = (64, 64)
    mode: str = "RGBA"
    preserve_aspect: bool = False


@dataclass(frozen=True)
class _ImageKey:
    path: str
    stamp: FileStamp
    generation: int
    transform: ImageTransform


@dataclass(frozen=True)
class _CacheKey:
    path: str
    stamp: FileStamp
    generation: int | None
    transform: ImageTransform


def _cache_key(key: _ImageKey) -> _CacheKey:
    # Stamped files survive catalog refreshes. Untracked paths need generation
    # because their zero stamp cannot distinguish a replacement on disk.
    generation = key.generation if key.stamp == FileStamp(0, 0, 0) else None
    return _CacheKey(key.path, key.stamp, generation, key.transform)


@dataclass(frozen=True)
class _Subscriber:
    generation: int
    callback: Callable[[object], None]


@dataclass
class _Pending:
    subscribers: dict[Hashable, _Subscriber]
    future: Future[object | None] | None = None


_MISSING = object()


def _candidate_paths(path: str) -> tuple[str, ...]:
    if not path.lower().endswith(".dds"):
        return (path,)
    stem = os.path.splitext(path)[0]
    return (path, *(stem + extension for extension in (".png", ".tga", ".jpg")))


def decode_image(path: str, transform: ImageTransform) -> object:
    if not PIL_OK or PILImage is None:
        raise RuntimeError("Pillow is not available")

    resampling = getattr(PILImage, "Resampling", PILImage)
    resample = getattr(
        resampling,
        "LANCZOS",
        getattr(PILImage, "LANCZOS", getattr(PILImage, "ANTIALIAS", 1)),
    )
    last_error: Exception | None = None
    for candidate in _candidate_paths(path):
        try:
            with PILImage.open(candidate) as source:
                image = source.convert(transform.mode)
                size = transform.size
                if transform.preserve_aspect:
                    width, height = image.size
                    ratio = min(size[0] / max(width, 1), size[1] / max(height, 1))
                    size = (max(1, int(width * ratio)), max(1, int(height * ratio)))
                return image.resize(size, resample)
        except (OSError, ValueError, RuntimeError, AttributeError, TypeError) as exc:
            last_error = exc
    if last_error is None:
        raise OSError(f"no image candidates for {path}")
    raise OSError(f"could not decode {path}: {last_error}") from last_error


def realize_photo_image(image: object) -> object:
    if PILImageTk is None:
        raise RuntimeError("Pillow ImageTk is not available")
    return PILImageTk.PhotoImage(image)


class ImageBroker:
    def __init__(
        self,
        executor: Executor,
        *,
        generation: Callable[[], int],
        decoder: Callable[[str, ImageTransform], object] = decode_image,
        realizer: Callable[[object], object] = realize_photo_image,
        pillow_available: bool = PIL_OK,
        cache_size: int = 512,
        pin_size: int = 512,
    ) -> None:
        if cache_size < 1 or pin_size < 1:
            raise ValueError("image cache and pin sizes must be positive")
        self._executor = executor
        self._generation = generation
        self._decoder = decoder
        self._realizer = realizer
        self._pillow_available = pillow_available
        self._cache_size = cache_size
        self._pin_size = pin_size
        self._owner_thread = threading.get_ident()
        self._lock = threading.Lock()
        self._cache: OrderedDict[_CacheKey, object | None] = OrderedDict()
        self._pins: OrderedDict[Hashable, tuple[_ImageKey, object]] = OrderedDict()
        self._pending: dict[_ImageKey, _Pending] = {}
        self._owner_requests: dict[Hashable, _ImageKey] = {}
        self._closed = False
        self._completed: queue.SimpleQueue[tuple[_ImageKey, object | None, bool]] = (
            queue.SimpleQueue()
        )

    @property
    def pending(self) -> bool:
        with self._lock:
            return bool(self._pending)

    @property
    def cache_count(self) -> int:
        with self._lock:
            return len(self._cache)

    @property
    def pin_count(self) -> int:
        with self._lock:
            return len(self._pins)

    def request(
        self,
        asset: AssetRef,
        path: str,
        *,
        transform: ImageTransform | None = None,
        owner: Hashable,
        callback: Callable[[object], None],
    ) -> object | None:
        if transform is None:
            transform = ImageTransform()
        key = _ImageKey(
            os.path.normcase(os.path.abspath(path)),
            asset.stamp,
            asset.generation,
            transform,
        )
        cache_key = _cache_key(key)
        on_owner_thread = threading.get_ident() == self._owner_thread
        pending: _Pending | None
        with self._lock:
            if self._closed:
                return None
            cached = self._cache.get(cache_key, _MISSING)
            if cached is not _MISSING:
                self._cache.move_to_end(cache_key)
                self._forget_request_locked(owner)
                if cached is not None and on_owner_thread:
                    self._pin_locked(owner, key, cached)
                    return cached
                # Deliver via the queue -- including a cached failure (None) so
                # the caller can render a placeholder instead of hanging.
                pending = self._pending.setdefault(key, _Pending({}))
                pending.subscribers[owner] = _Subscriber(asset.generation, callback)
                self._owner_requests[owner] = key
                self._completed.put((key, cached, True))
                return None

            self._forget_request_locked(owner)
            if not self._pillow_available:
                self._cache_locked(key, None)
                pending = self._pending.setdefault(key, _Pending({}))
                pending.subscribers[owner] = _Subscriber(asset.generation, callback)
                self._owner_requests[owner] = key
                self._completed.put((key, None, True))
                return None

            pending = self._pending.get(key)
            if pending is None:
                pending = _Pending({})
                self._pending[key] = pending
                future = self._executor.submit(self._decode, key)
                pending.future = future
                future.add_done_callback(self._queue_result_callback(key))
            pending.subscribers[owner] = _Subscriber(asset.generation, callback)
            self._owner_requests[owner] = key
        return None

    def release(self, owner: Hashable) -> None:
        with self._lock:
            self._forget_request_locked(owner)
            self._pins.pop(owner, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._pins.clear()
            self._owner_requests.clear()
            pending = tuple(self._pending.values())
            self._pending.clear()
            for request in pending:
                request.subscribers.clear()
                if request.future is not None:
                    request.future.cancel()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cache.clear()
            self._pins.clear()
            self._owner_requests.clear()
            pending = tuple(self._pending.values())
            self._pending.clear()
            for request in pending:
                if request.future is not None:
                    request.future.cancel()
        self._discard_completed()

    def drain(self) -> int:
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("image realization must run on the broker owner thread")

        with self._lock:
            if self._closed:
                self._discard_completed()
                return 0

        drained = 0
        while True:
            try:
                key, decoded, realized = self._completed.get_nowait()
            except queue.Empty:
                break
            drained += 1
            self._finish(key, decoded, realized=realized)
        return drained

    def _queue_result_callback(
        self, key: _ImageKey
    ) -> Callable[[Future[object | None]], None]:
        return lambda completed: self._queue_result(key, completed)

    def _decode(self, key: _ImageKey) -> object | None:
        try:
            return self._decoder(key.path, key.transform)
        except (OSError, RuntimeError, ValueError) as exc:
            log.debug("image decode failed for %s: %s", key.path, exc)
            return None

    def _queue_result(self, key: _ImageKey, future: Future[object | None]) -> None:
        if future.cancelled():
            return
        try:
            decoded = future.result()
        except OSError, ValueError, RuntimeError, AttributeError, TypeError:
            log.exception("image worker failed for %s", key.path)
            decoded = None
        if not self._closed:
            self._completed.put((key, decoded, False))

    def _discard_completed(self) -> None:
        while True:
            try:
                self._completed.get_nowait()
            except queue.Empty:
                return

    def _finish(
        self, key: _ImageKey, decoded: object | None, *, realized: bool
    ) -> None:
        current_generation = self._generation()
        with self._lock:
            pending = self._pending.pop(key, None)
            if pending is None:
                return
            subscribers = {
                owner: subscriber
                for owner, subscriber in pending.subscribers.items()
                if subscriber.generation == current_generation
                and self._owner_requests.get(owner) == key
            }
            for owner in pending.subscribers.keys() - subscribers.keys():
                if self._owner_requests.get(owner) == key:
                    self._owner_requests.pop(owner, None)
            if not subscribers:
                return

        photo = decoded if realized else None
        if decoded is not None and not realized:
            try:
                photo = self._realizer(decoded)
            except (
                OSError,
                ValueError,
                RuntimeError,
                AttributeError,
                TypeError,
            ):
                log.exception("image realization failed for %s", key.path)

        delivered = []
        with self._lock:
            if self._generation() != current_generation:
                for owner in subscribers:
                    if self._owner_requests.get(owner) == key:
                        self._owner_requests.pop(owner, None)
                return
            self._cache_locked(key, photo)
            for owner, subscriber in subscribers.items():
                if self._owner_requests.get(owner) != key:
                    continue
                self._owner_requests.pop(owner, None)
                if photo is not None:
                    self._pin_locked(owner, key, photo)
                # Deliver failures (photo is None) too, so the subscriber can
                # swap its loading placeholder for an error marker.
                delivered.append(subscriber)

        for subscriber in delivered:
            subscriber.callback(photo)

    def _forget_request_locked(self, owner: Hashable) -> None:
        previous = self._owner_requests.pop(owner, None)
        if previous is not None and previous in self._pending:
            pending = self._pending[previous]
            pending.subscribers.pop(owner, None)
            if (
                not pending.subscribers
                and pending.future is not None
                and pending.future.cancel()
            ):
                self._pending.pop(previous, None)

    def _cache_locked(self, key: _ImageKey, image: object | None) -> None:
        entry = _cache_key(key)
        self._cache[entry] = image
        self._cache.move_to_end(entry)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def _pin_locked(self, owner: Hashable, key: _ImageKey, image: object) -> None:
        self._pins[owner] = (key, image)
        self._pins.move_to_end(owner)
        while len(self._pins) > self._pin_size:
            self._pins.popitem(last=False)


__all__ = [
    "ImageBroker",
    "ImageTransform",
    "decode_image",
    "realize_photo_image",
]
