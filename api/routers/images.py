import uuid

from fastapi import APIRouter, Response

from tus_utils import get_image_path, get_image_metadata

images_router = APIRouter(
    prefix="/api/v1/images",
    tags=["images"],
    responses={404: {"description": "Not found"}},
)


@images_router.get("/{image_id}", responses={200: {"image": {}}}, response_class=Response)
def get_image(image_id: uuid.UUID):
    metadata = get_image_metadata(image_id)
    media_type = metadata.metadata.get("filetype", "image/jpeg")
    image_path = get_image_path(image_id)
    with image_path.open("rb") as f:
        image_bytes = f.read()
    return Response(content=image_bytes, media_type=media_type)
