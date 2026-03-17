import { useEffect, useRef, useState } from "react";
import "./AddPodcastDialog.scss";

interface SearchResult {
  name: string;
  artist: string | null;
  description: string | null;
  image_url: string | null;
  feed_url: string | null;
  genre: string | null;
  track_count: number | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSubscribed: () => void;
}

export default function AddPodcastDialog({
  open,
  onClose,
  onSubscribed,
}: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [subscribing, setSubscribing] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      setSelectedIndex(null);
      setSubscribing(false);
    }
  }, [open]);

  const handleQueryChange = (value: string) => {
    setQuery(value);
    setSelectedIndex(null);

    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!value.trim()) {
      setResults([]);
      return;
    }

    debounceRef.current = setTimeout(() => {
      fetch(`/search?q=${encodeURIComponent(value.trim())}`)
        .then((r) => r.json())
        .then(setResults)
        .catch(console.error);
    }, 400);
  };

  const handleSubscribe = async () => {
    if (selectedIndex === null) return;
    const selected = results[selectedIndex];
    if (!selected.feed_url) return;

    setSubscribing(true);
    try {
      const resp = await fetch("/podcasts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: selected.feed_url }),
      });
      if (resp.ok) {
        onSubscribed();
        onClose();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSubscribing(false);
    }
  };

  if (!open) return null;

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="header">
          <h2>Add Podcast</h2>
          <button className="close" onClick={onClose}>
            &times;
          </button>
        </div>

        <input
          className="search"
          type="text"
          placeholder="Search for a podcast..."
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          autoFocus
        />

        <div className="results">
          {results.map((r, i) => (
            <div
              key={i}
              className={`card${i === selectedIndex ? " card--selected" : ""}`}
              onClick={() => setSelectedIndex(i)}
            >
              {r.image_url ? (
                <img src={r.image_url} alt="" className="card-image" />
              ) : (
                <div className="card-image card-image--placeholder" />
              )}
              <div className="card-name">{r.name}</div>
              {r.artist && <div className="card-artist">{r.artist}</div>}
            </div>
          ))}
        </div>

        <div className="footer">
          <button
            className="subscribe"
            disabled={selectedIndex === null || subscribing}
            onClick={handleSubscribe}
          >
            {subscribing ? "Subscribing..." : "Subscribe to this Podcast"}
          </button>
        </div>
      </div>
    </div>
  );
}
