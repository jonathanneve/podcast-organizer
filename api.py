import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from psycopg.rows import dict_row
from chatbot import DocumentStore, LLMHandler
from episodes import build_full_summary, get_new_episodes, AUDIO_DIR
from database import get_db
from migrate import run_migrations
from models import Podcast, Episode
from rss import get_podcast_info, get_recent_episodes

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "3600"))

logger = logging.getLogger(__name__)

async def poll_new_episodes():
    """Periodically checks all subscribed podcasts for new episodes."""
    while True:
        logger.info("Polling all podcasts for new episodes")
        try:
            with get_db() as conn:
                conn.row_factory = dict_row
                podcasts = conn.execute("SELECT id, url FROM podcasts").fetchall()
                for podcast in podcasts:
                    try:
                        get_new_episodes(conn, podcast["id"], podcast["url"])
                    except Exception:
                        logger.exception("Failed to poll podcast %d", podcast["id"])
            logger.info("Finished polling %d podcasts", len(podcasts))
        except Exception:
            logger.exception("Error during episode polling cycle")
        await asyncio.sleep(POLL_INTERVAL)


document_store = DocumentStore()
llm = LLMHandler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    task = asyncio.create_task(poll_new_episodes())
    yield
    task.cancel()

app = FastAPI(title="Podcast Organizer API", lifespan=lifespan)

class PodcastCreate(BaseModel):
    url: str

class ChatRequest(BaseModel):
    question: str

@app.get("/podcasts", response_model=list[Podcast])
def list_podcasts():
    logger.info("Listing all podcasts")
    with get_db() as conn:
        conn.row_factory = dict_row
        podcasts = conn.execute("SELECT * FROM podcasts ORDER BY id").fetchall()
        logger.debug("Returning %d podcasts", len(podcasts))
        return podcasts

@app.get("/podcasts/{podcast_id}/episodes", response_model=list[Episode])
def list_episodes(podcast_id: int):
    logger.info("Listing episodes for podcast %d", podcast_id)
    with get_db() as conn:
        conn.row_factory = dict_row
        episodes = conn.execute(
            "SELECT * FROM episodes WHERE podcast_id = %s ORDER BY id",
            [podcast_id],
        ).fetchall()
        for episode in episodes:
            if episode['status'] == 'analyzed':
                episode["full_summary"] = build_full_summary(conn, episode["id"])
        logger.debug("Returning %d episodes for podcast %d", len(episodes), podcast_id)
        return episodes

@app.post("/podcasts", status_code=201, response_model=Podcast)
def create_podcast(podcast: PodcastCreate):
    logger.info("Creating podcast from feed: %s", podcast.url)
    info = get_podcast_info(podcast.url)
    logger.debug("Fetched podcast info: %s", info["title"])
    episodes = get_recent_episodes(podcast.url, n=10)
    logger.debug("Fetched %d episodes from feed", len(episodes))

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
            logger.debug("Created podcast %d with %d episodes", row["id"], len(episodes))

        return row

@app.post("/podcasts/{podcast_id}/more", response_model=list[Episode])
def fetch_more_episodes(podcast_id: int):
    logger.info("Fetching more episodes for podcast %d", podcast_id)
    with get_db() as conn:
        conn.row_factory = dict_row
        podcast = conn.execute(
            "SELECT url FROM podcasts WHERE id = %s", [podcast_id]
        ).fetchone()

        if not podcast:
            logger.warning("Podcast %d not found", podcast_id)
            raise HTTPException(status_code=404, detail="Podcast not found")

        logger.debug("Checking for new episodes of podcast %d", podcast_id)
        get_new_episodes(conn, podcast_id, podcast["url"])

        count_row = conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE podcast_id = %s", [podcast_id]
        ).fetchone()
        current_count = count_row[0] if count_row else 0

        logger.debug("Fetching the 10 latest episodes of podcast %d", podcast_id)
        candidates = get_recent_episodes(podcast["url"], n=10, skip=current_count)

        new_episodes = []
        for ep in candidates:
            row = conn.execute(
                "INSERT INTO episodes (podcast_id, url, description, image_url) VALUES (%s, %s, %s, %s) RETURNING *",
                [podcast_id, ep["url"], ep["description"], ep["image_url"]],
            ).fetchone()
            if row:
                new_episodes.append(row)

        logger.debug("Added %d more episodes for podcast %d", len(new_episodes), podcast_id)
        return new_episodes

@app.post("/podcasts/{podcast_id}/refresh", response_model=list[Episode])
def refresh_episodes(podcast_id: int):
    logger.info("Refreshing episodes for podcast %d", podcast_id)
    with get_db() as conn:
        conn.row_factory = dict_row
        podcast = conn.execute(
            "SELECT url FROM podcasts WHERE id = %s", [podcast_id]
        ).fetchone()

        if not podcast:
            logger.warning("Podcast %d not found", podcast_id)
            raise HTTPException(status_code=404, detail="Podcast not found")

        get_new_episodes(conn, podcast_id, podcast["url"])

        new_episodes = conn.execute(
            "SELECT * FROM episodes WHERE podcast_id = %s AND status = 'available' ORDER BY id",
            [podcast_id],
        ).fetchall()

        logger.debug("Found %d new episodes for podcast %d", len(new_episodes), podcast_id)
        return new_episodes

@app.get("/podcasts/{podcast_id}/episodes/{episode_id}/audio")
def stream_audio(podcast_id: int, episode_id: int):
    logger.info("Streaming audio for episode %d", episode_id)
    with get_db() as conn:
        conn.row_factory = dict_row
        episode = conn.execute(
            "SELECT audio_path FROM episodes WHERE id = %s", [episode_id]
        ).fetchone()

        if not episode:
            logger.warning("Episode %d not found for podcast %d", episode_id, podcast_id)
            raise HTTPException(status_code=404, detail="Episode not found")

        audio_path = episode["audio_path"]
        if not audio_path or not os.path.isfile(audio_path):
            logger.warning("Audio file %s not found", audio_path)
            raise HTTPException(status_code=404, detail="Audio file not available")

    return FileResponse(audio_path, media_type="audio/mpeg", filename=f"{episode_id}.mp3")

@app.post("/podcasts/{podcast_id}/episodes/{episode_id}/chat")
def chat_about_episode(podcast_id: int, episode_id: int, request: ChatRequest):
    logger.info("Chat question for episode %d: %s", episode_id, request.question)
    with get_db() as conn:
        conn.row_factory = dict_row
        episode = conn.execute(
            "SELECT transcript FROM episodes WHERE id = %s AND podcast_id = %s",
            [episode_id, podcast_id],
        ).fetchone()

        if not episode:
            logger.warning("Episode %d not found for podcast %d", episode_id, podcast_id)
            raise HTTPException(status_code=404, detail="Episode not found")

        if not episode["transcript"]:
            logger.warning("Episode %d of podcast %d has not been analyzed yet", episode_id, podcast_id)
            raise HTTPException(status_code=400, detail="Episode has not been analyzed yet")

    document_store.load_text(episode["transcript"])
    relevant_chunks = document_store.find_relevant_chunks(request.question)
    answer = llm.generate_response(request.question, relevant_chunks)

    logger.debug("Chat answer for episode %d: %s", episode_id, answer[:100])
    return {"answer": answer}
