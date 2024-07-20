from contextlib import asynccontextmanager
import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tusserver.tus import create_api_router

from api.routers.images import images_router
from db import sessionmanager

# TODO: settings class
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Function that handles startup and shutdown events.
    To understand more, read https://fastapi.tiangolo.com/advanced/events/
    """
    yield
    if sessionmanager._engine is not None:
        # Close the DB connection
        await sessionmanager.close()


app = FastAPI(lifespan=lifespan, title="pypix", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO: on_upload_complete handler for AI processing
app.include_router(
    create_api_router(
        files_dir="./images",
        location="http://127.0.0.1:8000/images/upload",
    ),
    prefix="/images/upload",
)

app.include_router(images_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", reload=True, port=8000)
