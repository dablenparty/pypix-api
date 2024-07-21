import uuid
from datetime import datetime, UTC
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, Index
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import mapped_column, Mapped

from . import DbBaseModel


class Image(DbBaseModel):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    exif_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now(UTC))
    caption: Mapped[Optional[str]] = mapped_column(Text)
    embeddings: Mapped[Optional[list]] = mapped_column(Vector(512), index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list())


Index("idx_images_tags", Image.tags, postgresql_using="gin")
