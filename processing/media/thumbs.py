"""The 96x72 JPEG thumbnail of a photo for `thumb:jpg` in the HBase catalogue.

The image work lives in `hbase.catalogue.thumbnail` (Task 12), so the catalogue load and the sample rows store
the same thumbnails.
"""

from __future__ import annotations

from hbase import catalogue

SIZE = catalogue.THUMB_SIZE


def thumbnail(data: bytes) -> bytes:
    """A 96x72 JPEG of the photo's bytes (cropped to 4:3 around the centre if needed), without EXIF."""
    return catalogue.thumbnail(bytes(data))
