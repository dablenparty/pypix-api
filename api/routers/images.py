import uuid

from fastapi import APIRouter, Response, HTTPException
from starlette import status

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

# TODO: search by embeddings
