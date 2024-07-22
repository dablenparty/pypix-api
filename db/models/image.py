import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, Index, func
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import mapped_column, Mapped

from . import DbBaseModel


class DbImage(DbBaseModel):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_name: Mapped[str] = mapped_column(String(255))
    exif_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    caption: Mapped[Optional[str]] = mapped_column(Text)
    embeddings: Mapped[Optional[list]] = mapped_column(Vector(512), index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)


Index("idx_images_tags", DbImage.tags, postgresql_using="gin")
