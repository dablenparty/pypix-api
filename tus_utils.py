import logging
import uuid
from pathlib import Path

from PIL import Image as PILImage
from sentence_transformers import SentenceTransformer
from sqlmodel import select
from starlette.requests import Request

from db import sessionmanager
from db.models.image import Image as ImageModel

FILES_DIR = "./images"


def tus_naming_function(_: Request, _metadata: dict[str, str]) -> str:
    raise NotImplementedError(
        "This will be implemented within the TUS server itself. This function should not be called anymore.")


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
        image_model = session.exec(select(ImageModel).where(ImageModel.id == image_id)).one()
        image_model.embeddings = embeddings
        session.add(image_model)
        session.commit()


def get_image_path(image_id: str | uuid.UUID):
    raise NotImplementedError("This function is not implemented yet.")


def get_image_metadata(image_id: str | uuid.UUID):
    raise NotImplementedError("This function is not implemented yet.")
