import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import cast

logger = logging.getLogger(__name__)

from psycopg import Connection
from psycopg.rows import DictRow

from rss import download_episode, get_recent_episodes
from cli.asr import transcribe_audio_file
from cli.topic_segmentation import segment_text
from cli.summarize import summarize_text


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


def _download_and_transcribe(audio_url: str, episode_id: int) -> tuple[str, str]:
    """Downloads episode audio to a persistent directory, transcribes it, and returns (audio_path, transcript)."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    audio_path = os.path.join(AUDIO_DIR, f"{episode_id}.mp3")

    download_episode(audio_url, audio_path)

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        transcript_path = tmp.name

    try:
        transcribe_audio_file(audio_path, transcript_path)
        with open(transcript_path, "r") as f:
            transcript = f.read()
    finally:
        os.unlink(transcript_path)

    return audio_path, transcript


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

        # 2. Download and transcribe
        logger.info("Episode %d: downloading and transcribing audio", episode_id)
        audio_path, transcript = _download_and_transcribe(episode["url"], episode_id)
        logger.info("Episode %d: transcription complete (%d characters)", episode_id, len(transcript))

        # 3. Segment the transcript into topics
        segments = segment_text(transcript)
        logger.info("Episode %d: segmented into %d topics", episode_id, len(segments))

        # 4. Summarize each segment in parallel threads, plus the overall summary
        segment_results: list[dict] = [{}] * len(segments)
        overall_summary = ""

        logger.info("Episode %d: summarizing %d segments in parallel", episode_id, len(segments))
        with ThreadPoolExecutor() as executor:
            # Submit segment summarization tasks
            segment_futures = {
                executor.submit(_summarize_segment, seg): i
                for i, seg in enumerate(segments)
            }

            # Submit overall summary task
            overall_future = executor.submit(
                summarize_text, transcript, 50, 200
            )

            # Collect segment results
            for future in as_completed(segment_futures):
                idx = segment_futures[future]
                segment_results[idx] = future.result()
                logger.debug("Episode %d: segment %d summarized", episode_id, idx)

            # Collect overall summary
            overall_result = cast(list[dict], overall_future.result())
            overall_summary = overall_result[0]["summary_text"] if overall_result else ""

        logger.info("Episode %d: all summaries complete", episode_id)

        # 5. Write segments to database
        for i, (seg_text, seg_result) in enumerate(zip(segments, segment_results)):
            conn.execute(
                """INSERT INTO episode_segments (episode_id, segment_order, transcript, topic, summary)
                   VALUES (%s, %s, %s, %s, %s)""",
                [episode_id, i, seg_text, seg_result["topic"], seg_result["summary"]],
            )

        # 6. Update the episode with transcript and summary
        conn.execute(
            "UPDATE episodes SET audio_path = %s, transcript = %s, summary = %s, status = 'ready' WHERE id = %s",
            [audio_path, transcript, overall_summary, episode_id],
        )
        conn.commit()
        logger.info("Episode %d: analysis complete, status set to ready", episode_id)

    except Exception:
        logger.exception("Episode %d: analysis failed", episode_id)
        conn.rollback()
        conn.execute(
            "UPDATE episodes SET status = 'available' WHERE id = %s",
            [episode_id],
        )
        conn.commit()
        raise


def build_full_summary(conn: Connection[DictRow], episode_id: int) -> str | None:
    segments = conn.execute(
        "SELECT topic, summary FROM episode_segments WHERE episode_id = %s ORDER BY segment_order",
        [episode_id],
    ).fetchall()
    if not segments:
        return None
    return "\n\n".join(
        f"{seg['topic']}\n{seg['summary']}" for seg in segments
    )