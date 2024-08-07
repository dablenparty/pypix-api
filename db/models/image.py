import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, Column, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import SQLModel, Field


class Image(SQLModel, table=True):
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    file_name: str
    caption: str | None = None
    embeddings: list[float] | None = Field(default=None, sa_column=Column(Vector(512)))
    created_at: datetime = Field(default_factory=datetime.now)
    tags: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String(20))))


# https://github.com/tiangolo/sqlmodel/discussions/571#discussioncomment-5332697
Index("idx_images_tags", Image.tags, postgresql_using="gin")
# index embeddings using vector_cosine_ops
Index("idx_images_embeddings",
      Image.embeddings,
      postgresql_using="ivfflat",
      postgresql_with={"lists": 100},
      postgresql_ops={"embeddings": "vector_cosine_ops"}
      )
