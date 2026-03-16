from datetime import datetime
from pydantic import BaseModel


class Podcast(BaseModel):
    id: int
    url: str
    title: str
    description: str | None = None
    image_url: str | None = None
    subscribed_at: datetime | None = None


class Episode(BaseModel):
    id: int
    podcast_id: int
    url: str
    description: str | None = None
    summary: str | None = None
    transcript: str | None = None
    image_url: str | None = None
    audio_path: str | None = None
    duration_seconds: int | None = None
    status: str = "available"
    full_summary: str | None = None
