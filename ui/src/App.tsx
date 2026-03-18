import { useEffect, useState } from "react";
import DOMPurify from "dompurify";
import AddPodcastDialog from "./AddPodcastDialog";
import EpisodeDetails from "./EpisodeDetails";
import "./App.scss";

function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html);
}

interface Podcast {
  id: number;
  url: string;
  title: string;
  description: string | null;
  image_url: string | null;
  subscribed_at: string | null;
}

interface Episode {
  id: number;
  podcast_id: number;
  url: string;
  title: string | null;
  description: string | null;
  summary: string | null;
  image_url: string | null;
  audio_path: string | null;
  status: string;
  full_summary: string | null;
}

export default function App() {
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchPodcasts = () => {
    fetch("/podcasts")
      .then((r) => r.json())
      .then(setPodcasts)
      .catch(console.error);
  };

  const fetchEpisodes = () => {
    if (!selectedId) return;
    fetch(`/podcasts/${selectedId}/episodes`)
      .then((r) => r.json())
      .then(setEpisodes)
      .catch(console.error);
  };

  useEffect(() => {
    fetchPodcasts();
  }, []);

  useEffect(() => {
    if (selectedId === null) {
      setEpisodes([]);
      setSelectedEpisodeId(null);
      return;
    }
    setSelectedEpisodeId(null);
    fetchEpisodes();
  }, [selectedId]);

  const [selectedEpisodeDetails, setSelectedEpisodeDetails] = useState<Episode | null>(null);

  useEffect(() => {
    if (selectedEpisodeId === null || selectedId === null) {
      setSelectedEpisodeDetails(null);
      return;
    }
    fetch(`/podcasts/${selectedId}/episodes/${selectedEpisodeId}`)
      .then((r) => r.json())
      .then(setSelectedEpisodeDetails)
      .catch(console.error);
  }, [selectedEpisodeId]);

  const fetchMoreEpisodes = async () => {
    if (!selectedId) return;
    setLoadingMore(true);
    try {
      const resp = await fetch(`/podcasts/${selectedId}/more`, {
        method: "POST",
      });
      if (resp.ok) {
        const newEpisodes: Episode[] = await resp.json();
        setEpisodes((prev) => [...prev, ...newEpisodes]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingMore(false);
    }
  };

  const deletePodcast = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const resp = await fetch(`/podcasts/${id}`, { method: "DELETE" });
      if (resp.ok) {
        if (selectedId === id) setSelectedId(null);
        fetchPodcasts();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const selected = podcasts.find((p) => p.id === selectedId) ?? null;

  return (
    <div className="app">
      <aside className="sidebar">
        <h2 className="title">Podcasts</h2>
        {podcasts.length === 0 && (
          <p className="empty">No subscriptions yet.</p>
        )}
        <ul className="list">
          {podcasts.map((p) => (
            <li
              key={p.id}
              className={`item${p.id === selectedId ? " item--selected" : ""}`}
              onClick={() => setSelectedId(p.id)}
            >
              {p.image_url ? (
                <img src={p.image_url} alt="" className="thumb" />
              ) : (
                <div className="thumb--placeholder" />
              )}
              <span className="item-title">{p.title}</span>
              <button className="delete-btn" onClick={(e) => deletePodcast(p.id, e)}>
                &times;
              </button>
            </li>
          ))}
        </ul>
        <div className="footer">
          <button className="add-btn" onClick={() => setDialogOpen(true)}>
            + Add Podcast
          </button>
        </div>
      </aside>

      <main className={`main${selectedEpisodeDetails ? " main--narrow" : ""}`}>
        {selected ? (
          <div>
            <h1>{selected.title}</h1>
            {selected.image_url && (
              <img
                src={selected.image_url}
                alt={selected.title}
                className="hero-image"
              />
            )}
            {selected.description && <p>{selected.description}</p>}

            <h2>Episodes</h2>
            {episodes.length === 0 ? (
              <p className="no-episodes">No episodes found.</p>
            ) : (
              <ul className="episode-list">
                {episodes.map((ep) => (
                  <li
                    key={ep.id}
                    className={`episode${ep.id === selectedEpisodeId ? " episode--selected" : ""}`}
                    onClick={() => setSelectedEpisodeId(ep.id)}
                  >
                    <div className="episode-info">
                      {ep.image_url && (
                        <img
                          src={ep.image_url}
                          alt=""
                          className="episode-thumb"
                        />
                      )}
                      <div className="episode-details">
                        <div className="episode-title">
                          {ep.title || `Episode ${ep.id}`}
                        </div>
                        {ep.description && (
                          <div
                            className="episode-desc"
                            dangerouslySetInnerHTML={{ __html: ep.description }}
                          />
                        )}
                        <span
                          className={`episode-status episode-status--${ep.status}`}
                        >
                          {ep.status}
                        </span>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <button
              className="more-btn"
              disabled={loadingMore}
              onClick={fetchMoreEpisodes}
            >
              {loadingMore ? "Loading..." : "Get More Episodes"}
            </button>
          </div>
        ) : (
          <p className="placeholder">
            Select a podcast from the sidebar to view details.
          </p>
        )}
      </main>

      {selectedEpisodeDetails && (
        <section className="episode-panel">
          <EpisodeDetails
            episode={selectedEpisodeDetails}
            onStatusChange={() => {
              fetchEpisodes();
              if (selectedId && selectedEpisodeId) {
                fetch(`/podcasts/${selectedId}/episodes/${selectedEpisodeId}`)
                  .then((r) => r.json())
                  .then(setSelectedEpisodeDetails)
                  .catch(console.error);
              }
            }}
          />
        </section>
      )}

      <AddPodcastDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onSubscribed={fetchPodcasts}
      />
    </div>
  );
}
