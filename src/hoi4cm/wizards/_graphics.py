from __future__ import annotations

import os
from pathlib import Path

from hoi4cm.mod.graphics_catalog import GraphicsCatalog

IMAGE_EXTENSIONS = (".dds", ".png", ".tga")


def browser_folders(
    folder: str,
    root_label: str,
    *,
    catalog: GraphicsCatalog | None,
) -> list[tuple[str, str]]:
    if catalog is None:
        return _filesystem_browser_folders(folder, root_label)

    folder_path = os.path.abspath(folder)
    direct_image = False
    child_names: set[str] = set()
    for path in catalog_image_paths(catalog, under=folder_path):
        relative = os.path.relpath(path, folder_path)
        parts = Path(relative).parts
        if len(parts) == 1:
            direct_image = True
        elif parts and parts[0] != os.pardir:
            child_names.add(parts[0])

    folders = [(root_label, folder)] if direct_image else []
    folders.extend((name, os.path.join(folder, name)) for name in sorted(child_names))
    return folders


def collect_image_pairs(
    folder: str,
    prefix: str,
    *,
    search: str = "",
    catalog: GraphicsCatalog | None,
    recursive: bool = True,
) -> list[tuple[str, str]]:
    if catalog is None:
        paths = _walk_image_paths(folder, recursive=recursive)
    else:
        paths = catalog_image_paths(catalog, under=folder)

    search_text = search.casefold()
    pairs = []
    for path in paths:
        if not recursive and not _same_directory(path, folder):
            continue
        filename = os.path.basename(path)
        if search_text and search_text not in filename.casefold():
            continue
        pairs.append((prefix + os.path.splitext(filename)[0], path))
    return pairs


def find_catalog_image(
    catalog: GraphicsCatalog,
    folder: str,
    stem: str,
    *,
    extensions: tuple[str, ...] = (".dds", ".tga", ".png"),
    recursive: bool = True,
) -> str | None:
    extension_order = {extension: index for index, extension in enumerate(extensions)}
    candidates = []
    for path in catalog_image_paths(catalog, under=folder):
        if not recursive and not _same_directory(path, folder):
            continue
        filename_stem, extension = os.path.splitext(os.path.basename(path))
        extension = extension.casefold()
        if (
            filename_stem.casefold() != stem.casefold()
            or extension not in extension_order
        ):
            continue
        relative = os.path.relpath(path, folder)
        depth = len(Path(relative).parts) - 1
        candidates.append(
            (
                depth,
                os.path.dirname(relative).casefold(),
                extension_order[extension],
                path.casefold(),
                path,
            )
        )
    if not candidates:
        return None
    return min(candidates)[-1]


def catalog_image_paths(catalog: GraphicsCatalog, *, under: str) -> tuple[str, ...]:
    return tuple(catalog.path_for(asset) for asset in catalog.query(under=under))


def _filesystem_browser_folders(folder: str, root_label: str) -> list[tuple[str, str]]:
    try:
        entries = os.listdir(folder)
    except OSError:
        return []

    folders = []
    if any(name.lower().endswith(IMAGE_EXTENSIONS) for name in entries):
        folders.append((root_label, folder))
    for name in sorted(entries):
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            folders.append((name, path))
    return folders


def _walk_image_paths(folder: str, *, recursive: bool) -> tuple[str, ...]:
    paths = []
    for root, directories, filenames in os.walk(folder):
        directories.sort()
        for filename in sorted(filenames):
            if filename.lower().endswith(IMAGE_EXTENSIONS):
                paths.append(os.path.join(root, filename))
        if not recursive:
            break
    return tuple(paths)


def _same_directory(path: str, folder: str) -> bool:
    return os.path.normcase(os.path.abspath(os.path.dirname(path))) == os.path.normcase(
        os.path.abspath(folder)
    )
