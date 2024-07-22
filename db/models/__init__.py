from sqlalchemy.orm import declarative_base

DbBaseModel = declarative_base()
metadata = DbBaseModel.metadata

# these MUST go below the declarative_base() call
from .image import DbImage
