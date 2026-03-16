from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from psycopg.rows import dict_row
from database import get_db
from migrate import run_migrations
from models import Podcast, Episode


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    yield


app = FastAPI(title="Podcast Organizer API", lifespan=lifespan)


class PodcastCreate(BaseModel):
    url: str
    title: str
    description: str | None = None


class EpisodeCreate(BaseModel):
    url: str
    description: str | None = None
    audio_path: str | None = None
    duration_seconds: int | None = None

@app.get("/podcasts", response_model=list[Podcast])
def list_podcasts():
    with get_db() as conn:
        conn.row_factory = dict_row
        return conn.execute("SELECT * FROM podcasts ORDER BY id").fetchall()


def build_full_summary(conn, episode_id: int) -> str | None:
    segments = conn.execute(
        "SELECT topic, summary FROM episode_segments WHERE episode_id = %s ORDER BY start_time",
        [episode_id],
    ).fetchall()
    if not segments:
        return None
    return "\n\n".join(
        f"{seg['topic']}\n{seg['summary']}" for seg in segments
    )


@app.get("/podcasts/{podcast_id}/episodes", response_model=list[Episode])
def list_episodes(podcast_id: int):
    with get_db() as conn:
        conn.row_factory = dict_row
        episodes = conn.execute(
            "SELECT * FROM episodes WHERE podcast_id = %s ORDER BY id",
            [podcast_id],
        ).fetchall()
        for episode in episodes:
            episode["full_summary"] = build_full_summary(conn, episode["id"])
        return episodes


@app.post("/podcasts", status_code=201, response_model=Podcast)
def create_podcast(podcast: PodcastCreate):
    with get_db() as conn:
        conn.row_factory = dict_row
        return conn.execute(
            "INSERT INTO podcasts (url, title, description) VALUES (%s, %s, %s) RETURNING *",
            [podcast.url, podcast.title, podcast.description],
        ).fetchone()


@app.post("/podcasts/{podcast_id}/episodes", status_code=201, response_model=Episode)
def create_episode(podcast_id: int, episode: EpisodeCreate):
    with get_db() as conn:
        conn.row_factory = dict_row
        return conn.execute(
            """INSERT INTO episodes (podcast_id, url, description, audio_path, duration_seconds)
               VALUES (%s, %s, %s, %s, %s) RETURNING *""",
            [podcast_id, episode.url, episode.description, episode.audio_path, episode.duration_seconds],
        ).fetchone()
