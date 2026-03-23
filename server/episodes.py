import json
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import cast
import numpy as np
from psycopg import Connection
from psycopg.rows import DictRow
from rss import download_episode, get_recent_episodes
from pipeline import segment_text, summarize_text, transcribe_audio_file
from chatbot import DocumentStore

_document_store: DocumentStore | None = None

def _get_document_store() -> DocumentStore:
    global _document_store
    if _document_store is None:
        _document_store = DocumentStore()
    return _document_store

logger = logging.getLogger(__name__)

def get_new_episodes(conn: Connection[DictRow], podcast_id: int, feed_url: str):
    """
    Checks the RSS feed for episodes not yet in the database and inserts them.
    """
    existing_urls = {
        row["url"]
        for row in conn.execute(
            "SELECT url FROM episodes WHERE podcast_id = %s", [podcast_id]
        ).fetchall()
    }

    feed_episodes = get_recent_episodes(feed_url)

    for ep in feed_episodes:
        if ep["url"] not in existing_urls:
            conn.execute(
                "INSERT INTO episodes (podcast_id, url, description, image_url) VALUES (%s, %s, %s, %s)",
                [podcast_id, ep["url"], ep["description"], ep["image_url"]],
            )

AUDIO_DIR = os.getenv("AUDIO_DIR", "audio")


def _download_and_transcribe(audio_url: str, episode_id: int) -> tuple[str, str, int, list[tuple[float, str]]]:
    """Downloads episode audio, transcribes it, and returns (audio_path, transcript, duration_seconds, timestamped_segments)."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    audio_path = os.path.join(AUDIO_DIR, f"{episode_id}.mp3")

    download_episode(audio_url, audio_path)

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        transcript_path = tmp.name

    try:
        duration_seconds, timestamped_segments = transcribe_audio_file(audio_path, transcript_path)
        with open(transcript_path, "r") as f:
            transcript = f.read()
    finally:
        os.unlink(transcript_path)

    return audio_path, transcript, duration_seconds, timestamped_segments


def _summarize_segment(segment_text_content: str) -> dict:
    """Generates a topic description and summary for a single segment."""
    topic_result = cast(list[dict], summarize_text(segment_text_content, min_length=3, max_length=15))
    summary_result = cast(list[dict], summarize_text(segment_text_content, min_length=30, max_length=120))

    topic = topic_result[0]["summary_text"] if topic_result else "Unknown topic"
    summary = summary_result[0]["summary_text"] if summary_result else ""

    return {"topic": topic, "summary": summary}


def analyze_episode(conn: Connection[DictRow], episode_id: int):
    """
    Runs the full analysis pipeline for an episode.
    """
    logger.info("Episode %d: starting analysis pipeline", episode_id)
    analysis_start = time.monotonic()
    conn.execute(
        "UPDATE episodes SET status = 'analyzing' WHERE id = %s",
        [episode_id],
    )
    conn.commit()

    try:
        # 1. Get the episode audio URL
        episode = conn.execute(
            "SELECT url FROM episodes WHERE id = %s", [episode_id]
        ).fetchone()
        if not episode:
            raise ValueError(f"Episode {episode_id} not found")

        with ThreadPoolExecutor() as executor:
            # 2. Download and transcribe in a background thread
            logger.info("Episode %d: downloading and transcribing audio", episode_id)
            transcribe_future = executor.submit(
                _download_and_transcribe, episode["url"], episode_id
            )

            audio_path, transcript, duration_seconds, timestamped_segments = transcribe_future.result()
            logger.info("Episode %d: transcription complete (%d characters)", episode_id, len(transcript))

            # 3. Segment the transcript into topics (temporarily disabled)
            # segments = segment_text(transcript, timestamped_segments)
            # logger.info("Episode %d: segmented into %d topics", episode_id, len(segments))

        # 4. Summarize each segment sequentially (temporarily disabled)
        # segment_results: list[dict] = []
        # logger.info("Episode %d: summarizing %d segments", episode_id, len(segments))
        #
        # for i, seg in enumerate(segments):
        #     segment_results.append(_summarize_segment(seg["text"]))
        #     logger.debug("Episode %d: segment %d summarized", episode_id, i)

        # 5. Generate overall summary
        overall_result = cast(list[dict], summarize_text(transcript, 100, 768))
        overall_summary = overall_result[0]["summary_text"] if overall_result else ""

        logger.info("Episode %d: overall summary complete", episode_id)

        # 6. Pre-compute chat embeddings
        logger.info("Episode %d: computing chat embeddings", episode_id)
        chunks, chunk_embeddings = _get_document_store().compute_embeddings(transcript)
        chunks_json = json.dumps(chunks)
        embeddings_bytes = chunk_embeddings.tobytes()
        embeddings_shape = chunk_embeddings.shape
        logger.info("Episode %d: computed %d chunk embeddings", episode_id, len(chunks))

        # 7. Write segments to database (temporarily disabled)
        # for i, (seg, seg_result) in enumerate(zip(segments, segment_results)):
        #     conn.execute(
        #         """INSERT INTO episode_segments (episode_id, segment_order, transcript, topic, summary, start_time)
        #            VALUES (%s, %s, %s, %s, %s, %s)""",
        #         [episode_id, i, seg["text"], seg_result["topic"], seg_result["summary"], seg["start_time"]],
        #     )

        # 8. Update the episode with transcript, summary, and embeddings
        analysis_duration = int(time.monotonic() - analysis_start)
        conn.execute(
            "UPDATE episodes SET audio_path = %s, transcript = %s, summary = %s, duration_seconds = %s, chunks = %s, chunk_embeddings = %s, analysis_duration_seconds = %s, status = 'ready' WHERE id = %s",
            [audio_path, transcript, overall_summary, duration_seconds, chunks_json, embeddings_bytes, analysis_duration, episode_id],
        )
        conn.commit()
        logger.info("Episode %d: analysis complete in %d seconds, status set to ready", episode_id, analysis_duration)

    except Exception:
        logger.exception("Episode %d: analysis failed", episode_id)
        conn.rollback()
        conn.execute(
            "UPDATE episodes SET status = 'available' WHERE id = %s",
            [episode_id],
        )
        conn.commit()
        raise


def _format_timestamp(seconds: int | None) -> str:
    if seconds is None:
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"[{h}:{m:02d}:{s:02d}] "
    return f"[{m}:{s:02d}] "


def build_full_summary(conn: Connection[DictRow], episode_id: int) -> str | None:
    segments = conn.execute(
        "SELECT topic, summary, start_time FROM episode_segments WHERE episode_id = %s ORDER BY segment_order",
        [episode_id],
    ).fetchall()
    if not segments:
        return None
    return "\n\n".join(
        f"{_format_timestamp(seg['start_time'])}{seg['topic']}\n{seg['summary']}" for seg in segments
    )