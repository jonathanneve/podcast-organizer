import { useCallback, useRef, useState } from "react";
import DOMPurify from "dompurify";

DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

function linkifyAndSanitize(html: string): string {
  const sanitized = DOMPurify.sanitize(html, { ADD_ATTR: ["target"] });
  // Convert plain-text URLs not already inside an <a> tag into clickable links
  return sanitized.replace(
    /(?<!href=["'])(?<!>)(https?:\/\/[^\s<]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
  );
}
import ChatPanel from "./ChatPanel";
import { Episode } from "./models";
import "./EpisodeDetails.scss";

interface Props {
  episode: Episode;
  onStatusChange: () => void;
}

export default function EpisodeDetails({ episode, onStatusChange }: Props) {
  const [analyzing, setAnalyzing] = useState(false);
  const [activeTab, setActiveTab] = useState<"summary" | "topics" | "transcript">("summary");
  const [topHeight, setTopHeight] = useState(33); // percentage
  const containerRef = useRef<HTMLDivElement>(null);

  const onSplitterMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const container = containerRef.current;
    if (!container) return;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const pct = ((moveEvent.clientY - rect.top) / rect.height) * 100;
      setTopHeight(Math.min(80, Math.max(10, pct)));
    };

    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, []);

  const audioUrl = `/podcasts/${episode.podcast_id}/episodes/${episode.id}/audio`;
  const isAnalyzed = episode.status === "analyzed" || episode.status === "ready";
  const isAnalyzing = episode.status === "analyzing";

  const startAnalysis = async () => {
    setAnalyzing(true);
    try {
      const resp = await fetch(
        `/podcasts/${episode.podcast_id}/episodes/${episode.id}/analyze`,
        { method: "POST" }
      );
      if (resp.ok) {
        onStatusChange();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setAnalyzing(false);
    }
  };

  const resetEpisode = async () => {
    try {
      const resp = await fetch(
        `/podcasts/${episode.podcast_id}/episodes/${episode.id}/reset`,
        { method: "POST" }
      );
      if (resp.ok) {
        onStatusChange();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const reanalyze = async () => {
    try {
      await fetch(
        `/podcasts/${episode.podcast_id}/episodes/${episode.id}/reset`,
        { method: "POST" }
      );
      const resp = await fetch(
        `/podcasts/${episode.podcast_id}/episodes/${episode.id}/analyze`,
        { method: "POST" }
      );
      if (resp.ok) {
        onStatusChange();
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="episode-details-panel" ref={containerRef}>
      <div className="top-section" style={{ height: `${topHeight}%` }}>
        <div className="top-row">
          {episode.image_url && (
            <img src={episode.image_url} alt="" className="ep-image" />
          )}
          <div className="ep-title-row">
            <h2 className="ep-title">{episode.title || `Episode ${episode.id}`}</h2>
            <span
              className={`ep-status ep-status--${episode.status}`}
              title={
                episode.analysis_duration_seconds
                  ? `Analysis took ${Math.floor(episode.analysis_duration_seconds / 60)}m ${episode.analysis_duration_seconds % 60}s`
                  : undefined
              }
            >
              {episode.status}
            </span>
          </div>
          {episode.audio_path && (
            <audio key={episode.id} controls className="audio-player">
              <source src={audioUrl} type="audio/mpeg" />
            </audio>
          )}
          {isAnalyzed && (
            <button className="reanalyze-btn" onClick={reanalyze} title="Re-analyze episode">
              ↻
            </button>
          )}
        </div>
        {episode.description && (
          <div
            className="ep-description"
            dangerouslySetInnerHTML={{
              __html: linkifyAndSanitize(episode.description),
            }}
          />
        )}
      </div>

      <div className="splitter" onMouseDown={onSplitterMouseDown} />

      {isAnalyzed ? (
        <div className="bottom-section">
          <div className="summary-panel">
            <div className="tab-bar">
              <button
                className={`tab${activeTab === "summary" ? " active" : ""}`}
                onClick={() => setActiveTab("summary")}
              >
                Summary
              </button>
              <button
                className={`tab${activeTab === "topics" ? " active" : ""}`}
                onClick={() => setActiveTab("topics")}
              >
                Topics
              </button>
              <button
                className={`tab${activeTab === "transcript" ? " active" : ""}`}
                onClick={() => setActiveTab("transcript")}
              >
                Transcript
              </button>
            </div>
            {activeTab === "summary" ? (
              episode.summary ? (
                <div className="summary-content">{episode.summary}</div>
              ) : (
                <p className="no-summary">No summary available.</p>
              )
            ) : activeTab === "topics" ? (
              episode.full_summary ? (
                <div className="summary-content">{episode.full_summary}</div>
              ) : (
                <p className="no-summary">No topics available.</p>
              )
            ) : (
              episode.transcript ? (
                <div className="summary-content">{episode.transcript}</div>
              ) : (
                <p className="no-summary">No transcript available.</p>
              )
            )}
          </div>

          <ChatPanel podcastId={episode.podcast_id} episodeId={episode.id} />
        </div>
      ) : (
        <div className="analyze-prompt">
          {isAnalyzing ? (
            <>
              <div className="analyze-spinner" />
              <h3>Analysis in progress...</h3>
              <p>
                The episode is being downloaded, transcribed, and summarized.
                This may take several minutes depending on the episode length.
              </p>
              <button className="abort-btn" onClick={resetEpisode}>
                Abort Analysis
              </button>
            </>
          ) : (
            <>
              <h3>This episode hasn't been analyzed yet</h3>
              <p>
                Analyze the episode to generate a transcript, summary, and enable
                the chat feature. This will download the audio, transcribe it,
                and break it into topic segments.
              </p>
              <button
                className="analyze-btn"
                onClick={startAnalysis}
                disabled={analyzing}
              >
                {analyzing ? "Starting..." : "Analyze Episode"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
