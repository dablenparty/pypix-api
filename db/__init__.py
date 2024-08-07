import contextlib
from collections.abc import Iterator
from os import getenv
from typing import Any, Annotated

from dotenv import load_dotenv, find_dotenv
from fastapi import Depends
from sqlalchemy import Connection
from sqlmodel import create_engine, Session, SQLModel

load_dotenv(find_dotenv())

SQLALCHEMY_DATABASE_URL = f"postgresql+psycopg2://postgres:{getenv("POSTGRESQL_PASSWORD")}@localhost:5432/postgres"


# from: https://medium.com/@tclaitken/setting-up-a-fastapi-app-with-async-sqlalchemy-2-0-pydantic-v2-e6c540be4308
class DatabaseSessionManager:
    def __init__(self, host: str, engine_kwargs: dict[str, Any] = None):
        if engine_kwargs is None:
            engine_kwargs = dict()
        self._engine = create_engine(host, **engine_kwargs)

    def init(self):
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")
        with self._engine.begin() as connection:
            SQLModel.metadata.create_all(connection)

    def close(self):
        if self._engine is None:
            return
        self._engine.dispose()

        self._engine = None

    @contextlib.contextmanager
    def connect(self) -> Iterator[Connection]:
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")

        with self._engine.begin() as connection:
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise

    @contextlib.contextmanager
    def session(self) -> Iterator[Session]:
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")

        session = Session(self._engine)
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _serializer(obj: Any) -> Any:
    from exifread.utils import Ratio
    if isinstance(obj, Ratio):
        return obj.decimal()
    raise TypeError(f"Object of type {type(obj)} is not serializable")


def _json_serializer(obj: Any) -> str:
    import json
    return json.dumps(obj, default=_serializer)


sessionmanager = DatabaseSessionManager(SQLALCHEMY_DATABASE_URL,
                                        {"json_serializer": _json_serializer})


def get_db_session():
    with sessionmanager.session() as session:
        yield session


DbSessionDependency = Annotated[Session, Depends(get_db_session)]
