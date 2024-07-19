from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from os import getenv

from dotenv import load_dotenv, find_dotenv

from .models import DbBaseModel

load_dotenv(find_dotenv())

SQLALCHEMY_DATABASE_URL = f"postgresql+psycopg2://postgres:{getenv("POSTGRESQL_PASSWORD")}@localhost:5432/postgres"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    from .models.image import Image
    # models must be imported to be created, thanks to python's import system
    DbBaseModel.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
