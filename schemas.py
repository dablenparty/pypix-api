import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Image(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_name: str
    exif_data: dict | None
    created_at: datetime
    caption: str | None
    embeddings: list | None
    tags: list[str] = list()
