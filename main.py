from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tusserver.tus import create_api_router

from db import init_db

init_db()

app = FastAPI()

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


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}
