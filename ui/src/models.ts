export interface Podcast {
  id: number;
  url: string;
  title: string;
  description: string | null;
  image_url: string | null;
  subscribed_at: string | null;
}

export interface Episode {
  id: number;
  podcast_id: number;
  url: string;
  title: string | null;
  description: string | null;
  summary: string | null;
  image_url: string | null;
  audio_path: string | null;
  transcript: string | null;
  status: string;
  full_summary: string | null;
  analysis_duration_seconds: number | null;
}
