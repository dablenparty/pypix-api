from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from os import getenv

from .models import DbBaseModel

SQLALCHEMY_DATABASE_URL = f"postgresql://postgres:{getenv("POSTGRESQL_PASSWORD")}@localhost:5432/postgres"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    DbBaseModel.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
