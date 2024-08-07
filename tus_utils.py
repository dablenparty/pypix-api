import json
import logging
import uuid
from pathlib import Path

from PIL import Image as PILImage
from sentence_transformers import SentenceTransformer
from sqlalchemy import insert, update, select
from starlette.requests import Request
from tusserver.metadata import FileMetadata as TusFileMetadata

from db import sessionmanager
from db.models.image import Image as ImageModel

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


def generate_embeddings(file_path: str | Path):
    model = SentenceTransformer("clip-ViT-B-32")
    image = PILImage.open(file_path)
    embeddings = model.encode(image)
    return embeddings


def tus_on_upload_complete(file_path: str, metadata: dict):
    try:
        embeddings = generate_embeddings(file_path)
    except Exception as e:
        logging.error(f"Failed to generate embeddings: {e}")
        embeddings = None
    with sessionmanager.session() as session:
        image_id = str(Path(file_path).stem)
        session.execute(
            update(ImageModel).where(ImageModel.id == image_id).values(exif_data=exif_tags, embeddings=embeddings)
        )
        session.commit()
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
