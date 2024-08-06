import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, Index, func
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import mapped_column, Mapped

from . import DbBaseModel


class ImageModel(DbBaseModel):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, init=False)
    file_name: Mapped[str] = mapped_column(String(255))
    caption: Mapped[Optional[str]] = mapped_column(Text)
    embeddings: Mapped[Optional[list]] = mapped_column(Vector(512))
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)


Index("idx_images_tags", ImageModel.tags, postgresql_using="gin")
# index embeddings usong vector_cosine_ops
Index("idx_images_embeddings",
      ImageModel.embeddings,
      postgresql_using="ivfflat",
      postgresql_with={"lists": 100},
      postgresql_ops={"embeddings": "vector_cosine_ops"}
      )
