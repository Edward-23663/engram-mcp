import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api import routes
from app.core.config import settings
from app.core.db import init_db
from app.core.redis import init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_redis()
    yield


app = FastAPI(
    title="FastAPI Application",
    description="Docker Compose Infrastructure Demo",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "fastapi"}


@app.get("/")
async def root():
    return {
        "message": "FastAPI Application",
        "docs": "/docs",
        "redoc": "/redoc"
    }
