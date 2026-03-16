import os
import feedparser
import requests


def _get_image_url(obj) -> str | None:
    image = getattr(obj, "image", None)
    if image and hasattr(image, "href"):
        return image.href
    return None


def get_podcast_info(feed_url: str) -> dict:
    """
    Returns the title and description of a podcast from its RSS feed.
    """
    feed = feedparser.parse(feed_url)
    return {
        "title": getattr(feed.feed, "title", "Unknown"),
        "description": getattr(feed.feed, "description", ""),
        "image_url": _get_image_url(feed.feed),
    }


def get_recent_episodes(feed_url: str, n: int = 10, skip: int = 0) -> list[dict]:
    """
    Returns the url, title and description of N episodes from a podcast RSS feed,
    skipping the first `skip` episodes.
    """
    feed = feedparser.parse(feed_url)
    fallback_image = _get_image_url(feed.feed)
    episodes = []
    for entry in feed.entries[skip:skip + n]:
        enclosures = getattr(entry, "enclosures", [])
        if not enclosures:
            continue
        episodes.append({
            "url": enclosures[0].href,
            "title": getattr(entry, "title", "Unknown"),
            "description": getattr(entry, "description", ""),
            "image_url": _get_image_url(entry) or fallback_image,
        })
    return episodes


def download_latest_episode(feed_url: str, output_dir: str = ".") -> dict:
    """
    Downloads the audio file from the latest episode of a podcast RSS feed.

    Returns a dict with episode metadata and the path to the downloaded file.
    """
    feed = feedparser.parse(feed_url)

    if not feed.entries:
        raise ValueError(f"No episodes found in feed: {feed_url}")

    latest = feed.entries[0]
    title = getattr(latest, "title", "Unknown")
    description = getattr(latest, "description", "")
    guid = getattr(latest, "guid", getattr(latest, "id", "unknown"))

    enclosures = getattr(latest, "enclosures", [])
    if not enclosures:
        raise ValueError(f"No audio enclosure found for episode: {title}")

    audio_url = enclosures[0].href
    file_name = f"{guid}.mp3"
    file_path = os.path.join(output_dir, file_name)

    os.makedirs(output_dir, exist_ok=True)

    with requests.get(audio_url, stream=True) as r:
        r.raise_for_status()
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    return {
        "title": title,
        "description": description,
        "guid": guid,
        "audio_url": audio_url,
        "audio_path": file_path,
    }
