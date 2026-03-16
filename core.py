from psycopg import Connection
from psycopg.rows import DictRow
from rss import get_recent_episodes


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

def analyze_episode(conn: Connection[DictRow], episode_id: int):
    """
    Runs the full analysis pipeline for an episode.
    """
    conn.execute(
        "UPDATE episodes SET status = 'analyzing' WHERE id = %s",
        [episode_id],
    )
    conn.commit()

    # TODO: Implement the analysis pipeline:
    # 1. Download the episode audio file
    # 2. Transcribe the audio to generate a full transcript
    # 3. Segment the transcript into topics
    # 4. For each segment:
    #    a. Generate a short topic description (a few words)
    #    b. Generate a detailed segment summary (2-5 sentences)
    #    c. Insert the segment into episode_segments
    # 5. Generate an overall episode summary from the full transcript
    # 6. Update the episode with the transcript and summary

    conn.execute(
        "UPDATE episodes SET status = 'ready' WHERE id = %s",
        [episode_id],
    )
    conn.commit()


def build_full_summary(conn: Connection[DictRow], episode_id: int) -> str | None:
    segments = conn.execute(
        "SELECT topic, summary FROM episode_segments WHERE episode_id = %s ORDER BY start_time",
        [episode_id],
    ).fetchall()
    if not segments:
        return None
    return "\n\n".join(
        f"{seg['topic']}\n{seg['summary']}" for seg in segments
    )