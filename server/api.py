import asyncio
import logging
import os
import threading
import json
import numpy as np

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from chatbot import DocumentStore, LLMHandler
from episodes import analyze_episode, build_full_summary, get_new_episodes, AUDIO_DIR
from database import get_db
from migrate import run_migrations
import requests as http_requests
from models import ChatRequest, Podcast, PodcastCreate, PodcastSearchResult, Episode
from rss import get_podcast_info, get_recent_episodes

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
logging.getLogger("httpx").setLevel(logging.WARNING)

for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    for handler in logging.getLogger(name).handlers:
        handler.setFormatter(formatter)

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

@app.get("/search", response_model=list[PodcastSearchResult])
def search_podcasts(q: str):
    logger.info("Searching podcasts for: %s", q)
    resp = http_requests.get(
        "https://itunes.apple.com/search",
        params={"term": q, "media": "podcast", "entity": "podcast"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    logger.debug("Found %d results for query: %s", len(results), q)
    return [
        PodcastSearchResult(
            name=r.get("collectionName"),
            artist=r.get("artistName"),
            description=r.get("description") or r.get("collectionName"),
            image_url=r.get("artworkUrl600") or r.get("artworkUrl100"),
            feed_url=r.get("feedUrl"),
            genre=r.get("primaryGenreName"),
            track_count=r.get("trackCount"),
            country=r.get("country"),
            content_advisory_rating=r.get("contentAdvisoryRating"),
            release_date=r.get("releaseDate"),
        )
        for r in results
    ]


@app.get("/podcasts", response_model=list[Podcast])
def list_podcasts():
    logger.info("Listing all podcasts")
    with get_db() as conn:
        conn.row_factory = dict_row
        podcasts = conn.execute("SELECT * FROM podcasts ORDER BY id").fetchall()
        logger.debug("Returning %d podcasts", len(podcasts))
        return podcasts

def _enrich_episode(conn, episode: dict) -> dict:
    if episode['status'] in ('analyzed', 'ready'):
        episode["full_summary"] = build_full_summary(conn, episode["id"])
    return episode

@app.get("/podcasts/{podcast_id}/episodes", response_model=list[Episode])
def list_episodes(podcast_id: int):
    logger.info("Listing episodes for podcast %d", podcast_id)
    with get_db() as conn:
        conn.row_factory = dict_row
        episodes = conn.execute(
            "SELECT * FROM episodes WHERE podcast_id = %s ORDER BY id",
            [podcast_id],
        ).fetchall()
        logger.debug("Returning %d episodes for podcast %d", len(episodes), podcast_id)
        return [_enrich_episode(conn, ep) for ep in episodes]

@app.get("/podcasts/{podcast_id}/episodes/{episode_id}", response_model=Episode)
def get_episode(podcast_id: int, episode_id: int):
    logger.info("Getting episode %d of podcast %d", episode_id, podcast_id)
    with get_db() as conn:
        conn.row_factory = dict_row
        episode = conn.execute(
            "SELECT * FROM episodes WHERE id = %s AND podcast_id = %s",
            [episode_id, podcast_id],
        ).fetchone()
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        return _enrich_episode(conn, episode)


@app.delete("/podcasts/{podcast_id}", status_code=204)
def delete_podcast(podcast_id: int):
    logger.info("Deleting podcast %d", podcast_id)
    with get_db() as conn:
        conn.execute("DELETE FROM episode_segments WHERE episode_id IN (SELECT id FROM episodes WHERE podcast_id = %s)", [podcast_id])
        conn.execute("DELETE FROM episodes WHERE podcast_id = %s", [podcast_id])
        result = conn.execute("DELETE FROM podcasts WHERE id = %s", [podcast_id])
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Podcast not found")


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
                    "INSERT INTO episodes (podcast_id, url, title, description, image_url) VALUES (%s, %s, %s, %s, %s)",
                    [row["id"], ep["url"], ep["title"], ep["description"], ep["image_url"]],
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
            "SELECT COUNT(*) AS cnt FROM episodes WHERE podcast_id = %s", [podcast_id]
        ).fetchone()
        current_count = count_row["cnt"] if count_row else 0

        logger.debug("Fetching the 10 latest episodes of podcast %d", podcast_id)
        candidates = get_recent_episodes(podcast["url"], n=10, skip=current_count)

        new_episodes = []
        for ep in candidates:
            row = conn.execute(
                "INSERT INTO episodes (podcast_id, url, title, description, image_url) VALUES (%s, %s, %s, %s, %s) RETURNING *",
                [podcast_id, ep["url"], ep["title"], ep["description"], ep["image_url"]],
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

@app.post("/podcasts/{podcast_id}/episodes/{episode_id}/analyze")
def analyze(podcast_id: int, episode_id: int):
    logger.info("Analyzing episode %d of podcast %d", episode_id, podcast_id)
    with get_db() as conn:
        conn.row_factory = dict_row
        episode = conn.execute(
            "SELECT status FROM episodes WHERE id = %s AND podcast_id = %s",
            [episode_id, podcast_id],
        ).fetchone()

        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")

        if episode["status"] != "available":
            raise HTTPException(status_code=409, detail=f"Episode is already {episode['status']}")

        conn.execute(
            "UPDATE episodes SET status = 'analyzing' WHERE id = %s",
            [episode_id],
        )

    def _run():
        try:
            with get_db() as bg_conn:
                bg_conn.row_factory = dict_row
                analyze_episode(bg_conn, episode_id)
        except Exception:
            logger.exception("Background analysis failed for episode %d", episode_id)

    threading.Thread(target=_run, daemon=True).start()

    return {"status": "ok"}

@app.post("/podcasts/{podcast_id}/episodes/{episode_id}/reset")
def reset_episode(podcast_id: int, episode_id: int):
    logger.info("Resetting episode %d of podcast %d", episode_id, podcast_id)
    with get_db() as conn:
        conn.row_factory = dict_row
        episode = conn.execute(
            "SELECT status FROM episodes WHERE id = %s AND podcast_id = %s",
            [episode_id, podcast_id],
        ).fetchone()

        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")

        if episode["status"] == "available":
            raise HTTPException(status_code=409, detail="Episode is already available")

        conn.execute(
            "DELETE FROM episode_segments WHERE episode_id = %s", [episode_id]
        )
        conn.execute(
            "DELETE FROM episode_chat WHERE episode_id = %s", [episode_id]
        )
        conn.execute(
            "UPDATE episodes SET status = 'available', transcript = NULL, summary = NULL, audio_path = NULL, duration_seconds = NULL, chunks = NULL, chunk_embeddings = NULL, analysis_duration_seconds = NULL WHERE id = %s",
            [episode_id],
        )

    return {"status": "ok"}


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

@app.get("/podcasts/{podcast_id}/episodes/{episode_id}/chat")
def get_chat_history(podcast_id: int, episode_id: int):
    logger.info("Getting chat history for episode %d", episode_id)
    with get_db() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT source, message, created_at FROM episode_chat WHERE episode_id = %s ORDER BY id",
            [episode_id],
        ).fetchall()
        return rows


@app.delete("/podcasts/{podcast_id}/episodes/{episode_id}/chat", status_code=204)
def clear_chat_history(podcast_id: int, episode_id: int):
    logger.info("Clearing chat history for episode %d", episode_id)
    with get_db() as conn:
        conn.execute("DELETE FROM episode_chat WHERE episode_id = %s", [episode_id])


@app.post("/podcasts/{podcast_id}/episodes/{episode_id}/chat")
def chat_about_episode(podcast_id: int, episode_id: int, request: ChatRequest):
    logger.info("Chat question for episode %d: %s", episode_id, request.question)
    with get_db() as conn:
        conn.row_factory = dict_row
        episode = conn.execute(
            "SELECT transcript, chunks, chunk_embeddings FROM episodes WHERE id = %s AND podcast_id = %s",
            [episode_id, podcast_id],
        ).fetchone()

        if not episode:
            logger.warning("Episode %d not found for podcast %d", episode_id, podcast_id)
            raise HTTPException(status_code=404, detail="Episode not found")

        if not episode["transcript"]:
            logger.warning("Episode %d of podcast %d has not been analyzed yet", episode_id, podcast_id)
            raise HTTPException(status_code=400, detail="Episode has not been analyzed yet")

    if not episode["chunks"] or not episode["chunk_embeddings"]:
        raise HTTPException(status_code=400, detail="Episode embeddings not available, please re-analyze")

    chunks = json.loads(episode["chunks"]) if isinstance(episode["chunks"], str) else episode["chunks"]
    raw = bytes(episode["chunk_embeddings"])
    embeddings = np.frombuffer(raw, dtype=np.float32).reshape(len(chunks), -1)
    document_store.load_precomputed(chunks, embeddings)

    relevant_chunks = document_store.find_relevant_chunks(request.question)
    answer = llm.generate_response(request.question, relevant_chunks)

    with get_db() as conn:
        conn.execute(
            "INSERT INTO episode_chat (episode_id, source, message) VALUES (%s, 'user', %s)",
            [episode_id, request.question],
        )
        conn.execute(
            "INSERT INTO episode_chat (episode_id, source, message) VALUES (%s, 'assistant', %s)",
            [episode_id, answer],
        )

    logger.debug("Chat answer for episode %d: %s", episode_id, answer[:100])
    return {"answer": answer}
