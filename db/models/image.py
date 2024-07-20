from datetime import datetime, UTC

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Uuid, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import mapped_column

from . import DbBaseModel


class Image(DbBaseModel):
    __tablename__ = "images"

    id = Column(Uuid, primary_key=True)
    file_name = Column(String(255), nullable=False)
    exif_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.now(UTC))
    caption = Column(Text, nullable=True)
    embeddings = mapped_column(Vector(512), nullable=True)
    tags = Column(ARRAY(Text), default=list(), nullable=False)


Index("idx_images_tags", Image.tags, postgresql_using="gin")
