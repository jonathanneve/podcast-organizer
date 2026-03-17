import { useEffect, useState } from "react";
import "./App.scss";

interface Podcast {
  id: number;
  url: string;
  title: string;
  description: string | null;
  image_url: string | null;
  subscribed_at: string | null;
}

export default function App() {
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    fetch("/podcasts")
      .then((r) => r.json())
      .then(setPodcasts)
      .catch(console.error);
  }, []);

  const selected = podcasts.find((p) => p.id === selectedId) ?? null;

  return (
    <div className="app">
      <aside className="sidebar">
        <h2 className="sidebar__title">Podcasts</h2>
        {podcasts.length === 0 && (
          <p className="sidebar__empty">No subscriptions yet.</p>
        )}
        <ul className="sidebar__list">
          {podcasts.map((p) => (
            <li
              key={p.id}
              className={`sidebar__item${p.id === selectedId ? " sidebar__item--selected" : ""}`}
              onClick={() => setSelectedId(p.id)}
            >
              {p.image_url ? (
                <img src={p.image_url} alt="" className="sidebar__thumb" />
              ) : (
                <div className="sidebar__thumb--placeholder" />
              )}
              <span className="sidebar__item-title">{p.title}</span>
            </li>
          ))}
        </ul>
      </aside>

      <main className="main">
        {selected ? (
          <div>
            <h1>{selected.title}</h1>
            {selected.image_url && (
              <img
                src={selected.image_url}
                alt={selected.title}
                className="main__hero-image"
              />
            )}
            {selected.description && <p>{selected.description}</p>}
          </div>
        ) : (
          <p className="main__placeholder">
            Select a podcast from the sidebar to view details.
          </p>
        )}
      </main>
    </div>
  );
}
