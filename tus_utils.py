import json
import logging
import uuid
from pathlib import Path

from PIL import Image
from sqlalchemy import insert
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


def tus_on_upload_complete(file_path: str, metadata: dict):
    ...


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
