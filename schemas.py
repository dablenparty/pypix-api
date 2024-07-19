from pydantic import BaseModel


class ImageBase(BaseModel):
    id: str
    file_name: str
    tags: list


class ImageCreate(ImageBase):
    pass


class Image(ImageBase):
    # TODO: exif typing
    exif_data: dict | None
    created_at: str
    caption: str | None
    embeddings: list | None

    class Config:
        orm_mode = True
