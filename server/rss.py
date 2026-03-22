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


def download_episode(audio_url: str, output_path: str):
    """
    Downloads an episode audio file from a direct URL to the given path.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with requests.get(audio_url, stream=True) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

