from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from psycopg.rows import dict_row
from core import build_full_summary, get_new_episodes
from database import get_db
from migrate import run_migrations
from models import Podcast, Episode
from rss import get_podcast_info, get_recent_episodes

@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    yield

app = FastAPI(title="Podcast Organizer API", lifespan=lifespan)

class PodcastCreate(BaseModel):
    url: str

@app.get("/podcasts", response_model=list[Podcast])
def list_podcasts():
    with get_db() as conn:
        conn.row_factory = dict_row
        return conn.execute("SELECT * FROM podcasts ORDER BY id").fetchall()

@app.get("/podcasts/{podcast_id}/episodes", response_model=list[Episode])
def list_episodes(podcast_id: int):
    with get_db() as conn:
        conn.row_factory = dict_row
        episodes = conn.execute(
            "SELECT * FROM episodes WHERE podcast_id = %s ORDER BY id",
            [podcast_id],
        ).fetchall()
        for episode in episodes:
            if episode['status'] == 'analyzed':
                episode["full_summary"] = build_full_summary(conn, episode["id"])
        return episodes

@app.post("/podcasts", status_code=201, response_model=Podcast)
def create_podcast(podcast: PodcastCreate):
    info = get_podcast_info(podcast.url)
    episodes = get_recent_episodes(podcast.url, n=10)

    with get_db() as conn:
        conn.row_factory = dict_row
        row = conn.execute(
            "INSERT INTO podcasts (url, title, description, image_url) VALUES (%s, %s, %s, %s) RETURNING *",
            [podcast.url, info["title"], info["description"], info["image_url"]],
        ).fetchone()

        if row:
            for ep in episodes:
                conn.execute(
                    "INSERT INTO episodes (podcast_id, url, description, image_url) VALUES (%s, %s, %s, %s)",
                    [row["id"], ep["url"], ep["description"], ep["image_url"]],
                )

        return row


@app.post("/podcasts/{podcast_id}/more", response_model=list[Episode])
def fetch_more_episodes(podcast_id: int):
    with get_db() as conn:
        conn.row_factory = dict_row
        podcast = conn.execute(
            "SELECT url FROM podcasts WHERE id = %s", [podcast_id]
        ).fetchone()

        if not podcast:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Podcast not found")

        get_new_episodes(conn, podcast_id, podcast["url"])

        count_row = conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE podcast_id = %s", [podcast_id]
        ).fetchone()
        current_count = count_row[0] if count_row else 0

        candidates = get_recent_episodes(podcast["url"], n=10, skip=current_count)

        new_episodes = []
        for ep in candidates:
            row = conn.execute(
                "INSERT INTO episodes (podcast_id, url, description, image_url) VALUES (%s, %s, %s, %s) RETURNING *",
                [podcast_id, ep["url"], ep["description"], ep["image_url"]],
            ).fetchone()
            if row:
                new_episodes.append(row)

        return new_episodes
