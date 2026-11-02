"""File discovery policies shared by mod scans and asset browsers."""

import glob
import os

IMAGE_EXTENSIONS = (".dds", ".png", ".tga")


def script_paths(
    directory: str, *, case_sensitive: bool = True, ignore_errors: bool = False
) -> list[str]:
    """List direct .txt paths, including hidden and directory entries."""
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        if ignore_errors:
            return []
        raise
    return [
        os.path.join(directory, name)
        for name in names
        if (name if case_sensitive else name.lower()).endswith(".txt")
    ]


def glob_script_paths(directory: str) -> list[str]:
    """Keep the platform's glob matching and error handling for wizard browsing."""
    return sorted(glob.glob(os.path.join(directory, "*.txt")))


def walk_image_paths(folder: str, *, recursive: bool = True) -> tuple[str, ...]:
    paths = []
    for root, directories, filenames in os.walk(folder):
        directories.sort()
        for filename in sorted(filenames):
            if filename.lower().endswith(IMAGE_EXTENSIONS):
                paths.append(os.path.join(root, filename))
        if not recursive:
            break
    return tuple(paths)


def flat_image_paths(folder: str) -> tuple[str, ...]:
    """List image-suffixed entries without hiding directory read errors."""
    return tuple(
        os.path.join(folder, name)
        for name in sorted(os.listdir(folder))
        if name.lower().endswith(IMAGE_EXTENSIONS)
    )
