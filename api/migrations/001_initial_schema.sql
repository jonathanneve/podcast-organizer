CREATE TABLE podcasts (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    subscribed_at TIMESTAMP DEFAULT now()
);

CREATE TABLE episodes (
    id SERIAL PRIMARY KEY,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id),
    url TEXT NOT NULL,
    description TEXT,
    summary TEXT,
    transcript TEXT,
    audio_path TEXT,
    duration_seconds INTEGER,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'analyzing', 'ready'))
);

CREATE TABLE episode_segments (
    id SERIAL PRIMARY KEY,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    start_time INTEGER NOT NULL,
    end_time INTEGER NOT NULL,
    transcript TEXT,
    summary TEXT,
    topic TEXT
);
