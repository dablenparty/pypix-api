import uuid

import exifread
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from starlette import status
from starlette.responses import FileResponse

from db import DbSessionDependency
from db.models.image import Image as ImageModel
from tus_utils import get_image_path, get_image_metadata

images_router = APIRouter(
    prefix="/api/v1/images",
    tags=["images"],
    responses={status.HTTP_404_NOT_FOUND: {"message": "Not found"}},
)


@images_router.get("/", response_model=list[ImageModel], status_code=status.HTTP_200_OK)
def get_images(*, db_session: DbSessionDependency):
    images = db_session.exec(select(ImageModel)).all()
    return images


@images_router.get("/{image_id}", response_class=FileResponse, status_code=status.HTTP_200_OK)
def get_image(image_id: uuid.UUID):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


@images_router.get("/{image_id}/exif", response_model=dict, status_code=status.HTTP_200_OK)
def get_image_exif(image_id: uuid.UUID):
    file_path = get_image_path(image_id)
    with open(file_path, "rb") as f:
        # per docs: expects an open file object
        # details=False to avoid loading the entire file
        exif_tags = exifread.process_file(f, details=False)
    structured_exif = {}
    for tag, value in exif_tags.items():
        first, second = tag.split(" ")
        real_value = value.values
        structured_exif.setdefault(first, {})[second] = real_value
    return structured_exif


@images_router.get("/{image_id}/data", response_model=ImageModel, status_code=status.HTTP_200_OK)
def get_image_data(image_id: uuid.UUID, db_session: DbSessionDependency):
    image = db_session.scalars(select(ImageModel).where(ImageModel.id == image_id)).one_or_none()
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found in database")
    return image


@images_router.get("/{image_id}/search", response_model=list[ImageModel], status_code=status.HTTP_200_OK)
def search_images(image_id: uuid.UUID, query: str | None, db_session: DbSessionDependency):
    # TODO: search by embeddings
    # when query is None, return all images
    # otherwise, do a cosine similarity search
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")
