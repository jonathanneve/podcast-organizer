from datetime import datetime
from pydantic import BaseModel


class Podcast(BaseModel):
    id: int
    url: str
    title: str
    description: str | None = None
    image_url: str | None = None
    subscribed_at: datetime | None = None


class PodcastCreate(BaseModel):
    url: str


class ChatRequest(BaseModel):
    question: str


class PodcastSearchResult(BaseModel):
    name: str
    artist: str | None = None
    description: str | None = None
    image_url: str | None = None
    feed_url: str | None = None
    genre: str | None = None
    track_count: int | None = None
    country: str | None = None
    content_advisory_rating: str | None = None
    release_date: str | None = None


class Episode(BaseModel):
    id: int
    podcast_id: int
    url: str
    title: str | None = None
    description: str | None = None
    summary: str | None = None
    transcript: str | None = None
    image_url: str | None = None
    audio_path: str | None = None
    duration_seconds: int | None = None
    status: str = "available"
    full_summary: str | None = None
