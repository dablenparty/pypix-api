from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class DbBaseModel(MappedAsDataclass, DeclarativeBase):
    """Base class for all database models"""
    pass


# these MUST go below the class definition
from .image import ImageModel
