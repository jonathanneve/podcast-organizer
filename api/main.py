from contextlib import asynccontextmanager
from fastapi import FastAPI
from migrate import run_migrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    yield


app = FastAPI(title="Podcast Organizer API", lifespan=lifespan)


@app.get("/health")
def health_check():
    return {"status": "ok"}
