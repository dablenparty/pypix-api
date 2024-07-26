import uuid

from fastapi import APIRouter, Response, HTTPException
from sqlalchemy import select
from starlette import status

from db import DbSessionDependency
from db.models import ImageModel
from tus_utils import get_image_path, get_image_metadata

images_router = APIRouter(
    prefix="/api/v1/images",
    tags=["images"],
    responses={status.HTTP_404_NOT_FOUND: {"message": "Not found"}},
)


@images_router.get("/{image_id}", response_class=Response, status_code=status.HTTP_200_OK)
def get_image(image_id: uuid.UUID):
    try:
        metadata = get_image_metadata(image_id)
        media_type = metadata.metadata.get("filetype", "image/jpeg")
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    image_path = get_image_path(image_id)
    with image_path.open("rb") as f:
        image_bytes = f.read()
    return Response(content=image_bytes, media_type=media_type)


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
    raise NotImplementedError("Search by embeddings is not implemented yet")

