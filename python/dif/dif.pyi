class ImageHash:
    bool_values: list[bool]
    valueus: list[int]
    hash_size: int

    def distance(self, other: ImageHash) -> int: ...

def hash_image(fpath: str, hash_size: int) -> ImageHash: ...
