from collections import defaultdict
import mimetypes
import os
from typing import Annotated, Callable, Dict, List, Optional
from typing_extensions import TypeVarTuple, Unpack

from dif import ImageHash

Path = Annotated[str, "Path to file"]
FileHashes = Dict[Path, Optional[ImageHash]]
FileDuplicates = Dict[Path, List[Path]]
Ts = TypeVarTuple("Ts")


def get_all_images(folder: Path) -> List[str]:
    """Get all image files from a folder."""
    image_paths: List[str] = []

    for root, _, files in os.walk(folder):
        full_root = os.path.join(folder, root)

        for filename in files:
            file_path = os.path.join(full_root, filename)
            mime = mimetypes.guess_type(file_path)[0]
            if not mime or not (mime and mime.startswith("image")):
                continue

            image_paths.append(file_path)
    return image_paths


def get_hashes(
    image_paths: List[Path],
    hash_size: int,
    hash_func: Callable[[str, int, Unpack[Ts]], ImageHash],
    *args: Unpack[Ts],
    increment_func: Optional[Callable] = None,
) -> FileHashes:
    hashes: FileHashes = {}
    for file_path in image_paths:
        try:
            hashes[file_path] = hash_func(file_path, hash_size, *args)
        except:
            hashes[file_path] = None

        if increment_func:
            increment_func()

    return hashes


def find_duplicates(
    image_paths: List[str],
    hashes: FileHashes,
    hash_size: int,
    threshold: float,
    increment_func: Optional[Callable] = None,
) -> FileDuplicates:
    """Find duplicates from list of images."""
    dups: FileDuplicates = defaultdict(list)

    img_len = len(image_paths)
    for i in range(img_len):
        base = image_paths[i]
        base_hash = hashes[base]
        if base_hash is None:
            if increment_func:
                increment_func()
            continue

        for j in range(i + 1, img_len):
            target = image_paths[j]
            target_hash = hashes[target]
            if target_hash is None:
                continue

            total_len = hash_size**2
            if base_hash.distance(target_hash) / total_len < threshold:
                dups[base].append(target)

        if increment_func:
            increment_func()

    final_hashes = {k: v for k, v in dups.items() if len(v) > 1}
    return final_hashes
