import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from db import DbSessionDependency
from db.models import Image

images_router = APIRouter(
    prefix="/api/v1/images",
    tags=["images"],
    responses={404: {"description": "Not found"}},
)


@images_router.get("/{image_id}")
async def get_image(image_id: uuid.UUID, db_session: DbSessionDependency):
    image = (await db_session.scalars(select(Image).where(Image.id == image_id))).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return image
