import json
import uuid
from pathlib import Path
from typing import Any

import exifread
from sqlalchemy import insert, update
from starlette.requests import Request
from tusserver.metadata import FileMetadata as TusFileMetadata

from db import sessionmanager
from db.models import ImageModel

FILES_DIR = "./images"


def tus_naming_function(_: Request, metadata: dict[str, str]) -> str:
    if not metadata or "filename" not in metadata:
        raise ValueError("metadata.filename is required")
    file_name = metadata["filename"]
    with sessionmanager.session() as session:
        image_id = session.scalars(insert(ImageModel).returning(ImageModel.id), [{"file_name": file_name}]).one()
        # force commit
        session.commit()
        session.flush()
    return str(image_id)


def process_exif(file_path: str | Path) -> dict[str, dict[str, Any]]:
    with open(file_path, "rb") as f:
        exif_tags = exifread.process_file(f, details=False)
    sanitized_exif = {}
    for tag, value in exif_tags.items():
        first, second = tag.split(" ")
        real_value = value.values
        sanitized_exif.setdefault(first, {})[second] = real_value
    return sanitized_exif


def tus_on_upload_complete(file_path: str, metadata: dict):
    # TODO: extract a dataclass for exif tags
    # you can probably codegen this with metaprogramming
    exif_tags = process_exif(file_path)
    with sessionmanager.session() as session:
        image_id = str(Path(file_path).stem)
        session.execute(
            update(ImageModel).where(ImageModel.id == image_id).values(exif_data=exif_tags)
        )
        session.commit()
        from sqlalchemy import select
        image = session.scalars(select(ImageModel).where(ImageModel.id == image_id)).one()
        print(image)


def get_image_path(image_id: str | uuid.UUID) -> Path:
    return Path(FILES_DIR) / str(image_id)


def get_image_metadata(image_id: str | uuid.UUID) -> TusFileMetadata:
    # TODO: the current tus server implementation uses a non-standard suffix for json files
    meta_path = get_image_path(image_id).with_suffix(".info")
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata file not found for image {image_id}")
    with meta_path.open() as f:
        metadata = json.load(f)
    return TusFileMetadata(**metadata)


if __name__ == '__main__':
    tus_on_upload_complete(r"D:\github\pypix-api\images\85e3131f-276d-499f-8d50-c9865dd6d2f0", {})
