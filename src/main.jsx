import { useMemo, useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { DEMO_ARRANGEMENT } from "./data/demoArrangement";
import { youtubeEmbedUrl, youtubeVideoId } from "./lib/trackInput";

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const NOTE_INDEX = {
  C: 0,
  "B#": 0,
  "C#": 1,
  Db: 1,
  D: 2,
  "D#": 3,
  Eb: 3,
  E: 4,
  Fb: 4,
  F: 5,
  "E#": 5,
  "F#": 6,
  Gb: 6,
  G: 7,
  "G#": 8,
  Ab: 8,
  A: 9,
  "A#": 10,
  Bb: 10,
  B: 11,
  Cb: 11,
};

function transposeChord(chord, semitones) {
  if (!semitones || chord === "—") return chord;

  return chord.replace(/(^|\/)([A-G](?:#|b)?)/g, (match, prefix, root) => {
    const index = NOTE_INDEX[root];
    if (index === undefined) return match;
    return `${prefix}${NOTE_NAMES[(index + semitones + 12) % 12]}`;
  });
}



function Icon({ children, className = "" }) {
  return <span className={`icon ${className}`} aria-hidden="true">{children}</span>;
}

function App() {
  const [videoLink, setVideoLink] = useState("");
  const [status, setStatus] = useState("idle");
  const [arrangement, setArrangement] = useState(DEMO_ARRANGEMENT);
  const [transposition, setTransposition] = useState(0);
  const [instrument, setInstrument] = useState("Ukulele");
  const [editMode, setEditMode] = useState(false);
  const [toast, setToast] = useState("");
  const [analysisError, setAnalysisError] = useState("");
  
  // Real-time synchronization state & refs
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  
  const playerRef = useRef(null);
  const pollingRef = useRef(null);
  const lastScrolledBarRef = useRef(-1);

  const videoId = useMemo(() => youtubeVideoId(videoLink), [videoLink]);
  const hasVideo = Boolean(videoId) && status !== "idle" && status !== "invalid";
  const hasGeneratedChart = status === "ready";
  const title = hasGeneratedChart ? arrangement.title : hasVideo ? "YouTube video ready" : arrangement.title;

  // Load YouTube Iframe API script dynamically
  useEffect(() => {
    if (window.YT) return;
    const tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    const firstScriptTag = document.getElementsByTagName("script")[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
  }, []);

  // Initialize/Update player instance
  useEffect(() => {
    if (!hasVideo || !videoId) {
      if (playerRef.current) {
        try {
          playerRef.current.destroy();
        } catch (e) {}
        playerRef.current = null;
      }
      return;
    }

    const initPlayer = () => {
      if (!window.YT || !window.YT.Player) {
        setTimeout(initPlayer, 100);
        return;
      }

      const container = document.getElementById("youtube-player-container");
      if (!container) {
        setTimeout(initPlayer, 100);
        return;
      }

      if (playerRef.current && typeof playerRef.current.loadVideoById === "function") {
        try {
          playerRef.current.loadVideoById(videoId);
          return;
        } catch (e) {}
      }

      playerRef.current = new window.YT.Player("youtube-player-container", {
        height: "100%",
        width: "100%",
        videoId: videoId,
        events: {
          onStateChange: (event) => {
            if (event.data === window.YT.PlayerState.PLAYING) {
              setIsPlaying(true);
            } else {
              setIsPlaying(false);
            }
          },
        },
      });
    };

    initPlayer();
  }, [videoId, hasVideo]);

  // Polling current time
  useEffect(() => {
    if (!isPlaying) {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }

    pollingRef.current = setInterval(() => {
      if (playerRef.current && typeof playerRef.current.getCurrentTime === "function") {
        setCurrentTime(playerRef.current.getCurrentTime());
      }
    }, 100);

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [isPlaying]);

  // Compute active event index
  const activeEventIndex = useMemo(() => {
    if (!arrangement.timing || currentTime === null) return -1;
    for (let i = 0; i < arrangement.timing.length; i++) {
      const event = arrangement.timing[i];
      if (currentTime >= event.start && currentTime < event.end) {
        return i;
      }
    }
    return -1;
  }, [arrangement.timing, currentTime]);

  // Scroll active event into view
  useEffect(() => {
    if (activeEventIndex !== -1 && activeEventIndex !== lastScrolledBarRef.current) {
      lastScrolledBarRef.current = activeEventIndex;
      const activeEl = document.querySelector(".chord-block.active");
      if (activeEl) {
        activeEl.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
      }
    }
  }, [activeEventIndex]);

  function showToast(message) {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!videoId) {
      setStatus("invalid");
      return;
    }

    setStatus("loading");
    setAnalysisError("");
    try {
      const response = await fetch("http://127.0.0.1:8000/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: videoLink }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Chord analysis could not be completed.");
      setArrangement(result);
      setStatus("ready");
    } catch (error) {
      setAnalysisError(error.message || "Chord analysis could not be completed.");
      setStatus("error");
    }
  }

  function copyChart() {
    const body = arrangement.timing
      ? arrangement.timing.map((event) => transposeChord(event.chord, transposition)).join("  |  ")
      : "";
    if (!navigator.clipboard) {
      showToast("Select and copy the chart from the screen");
      return;
    }
    navigator.clipboard.writeText(body).then(
      () => showToast("Chord chart copied"),
      () => showToast("Select and copy the chart from the screen"),
    );
  }

  function updateChord(eventIndex, nextChord) {
    setArrangement((current) => ({
      ...current,
      timing: current.timing.map((event, i) => {
        if (i !== eventIndex) return event;
        return { ...event, chord: nextChord };
      }),
    }));
  }

  return (
    <main className="app-shell">
      <div className="aurora aurora-one" />
      <div className="aurora aurora-two" />

      <nav className="topbar">
        <a className="brand" href="#top" aria-label="AnyChords home">
          <span className="brand-mark"><span>♩</span></span>
          <span>AnyChords</span>
        </a>

        {hasVideo && (
          <div className="topbar-search-wrapper">
            <form className="link-card" onSubmit={handleSubmit}>
              <div className="link-icon"><Icon>↗</Icon></div>
              <label className="visually-hidden" htmlFor="youtube-link-topbar">YouTube video link</label>
              <input
                id="youtube-link-topbar"
                value={videoLink}
                onChange={(event) => {
                  setVideoLink(event.target.value);
                  if (["invalid", "error"].includes(status)) setStatus("idle");
                }}
                placeholder="Paste a YouTube video link"
                autoComplete="off"
              />
              <button className="primary-button" type="submit" disabled={status === "loading"}>
                {status === "loading" ? "Analysing…" : "Make chart"}
                {status !== "loading" && <Icon>→</Icon>}
              </button>
            </form>
            {status === "invalid" && <p className="input-error">Use a YouTube video URL, such as youtube.com/watch?v=…</p>}
            {analysisError && <p className="input-error">{analysisError}</p>}
          </div>
        )}

        <div className="topbar-actions">
          <button className="text-button" type="button" onClick={() => showToast("Your library is coming next.")}>Library</button>
          <button className="avatar" type="button" aria-label="Open account menu">P</button>
        </div>
      </nav>

      {!hasVideo && (
        <section className="hero" id="top">
          <div className="eyebrow"><span className="pulse-dot" /> CHORDS, MADE PLAYABLE</div>
          <h1>Bring any song<br /><em>to your hands.</em></h1>
          <p>Start with a YouTube video. We’ll use its audio source to build a playable chord chart.</p>

          <form className="link-card" onSubmit={handleSubmit}>
            <div className="link-icon"><Icon>↗</Icon></div>
            <label className="visually-hidden" htmlFor="youtube-link">YouTube video link</label>
            <input
              id="youtube-link"
              value={videoLink}
              onChange={(event) => {
                setVideoLink(event.target.value);
                if (["invalid", "error"].includes(status)) setStatus("idle");
              }}
              placeholder="Paste a YouTube video link"
              autoComplete="off"
            />
            <button className="primary-button" type="submit" disabled={status === "loading"}>
              {status === "loading" ? "Analysing audio…" : "Make my chart"}
              {status !== "loading" && <Icon>→</Icon>}
            </button>
          </form>
          {status === "invalid" && <p className="input-error">Use a YouTube video URL, such as youtube.com/watch?v=…</p>}
          {analysisError && <p className="input-error">{analysisError}</p>}
          <p className="helper-copy">The video is the audio source. Chord analysis will be shown only once it has been generated.</p>
        </section>
      )}

      {hasVideo && (
        <section className="workspace" aria-label="Chord chart workspace">
          <aside className="song-panel">
            {hasVideo ? (
              <div className="video-frame">
                <div id="youtube-player-container" style={{ width: "100%", height: "100%" }} />
              </div>
            ) : <div className="cover-art" aria-hidden="true">
              <span className="cover-sun" />
              <span className="cover-line line-one" />
              <span className="cover-line line-two" />
              <span className="cover-title">ANY<br />CHORDS</span>
            </div>}
            <div className="song-intro">
              <span className="status-pill"><span /> {hasGeneratedChart ? "Automatic chord draft" : hasVideo ? "Video source linked" : "Preview arrangement"}</span>
              <h2>{title}</h2>
              {hasVideo ? (
                <p><a className="track-link" href={videoLink} target="_blank" rel="noreferrer">Open on YouTube <Icon>↗</Icon></a>{hasGeneratedChart ? " · local analysis" : " · ready for analysis"}</p>
              ) : <p>{arrangement.artist}</p>}
            </div>

            <dl className="song-facts">
              <div><dt>Key</dt><dd>{transposition === 0 ? arrangement.key : `${NOTE_NAMES[(NOTE_INDEX.C + transposition + 12) % 12]} major`}</dd></div>
              <div><dt>Tempo</dt><dd>{arrangement.tempo} BPM</dd></div>
              <div><dt>Meter</dt><dd>{arrangement.meter}</dd></div>
            </dl>

            <div className="confidence-card">
              <div className="confidence-title"><span><Icon>✦</Icon> Chart status</span><b>{hasGeneratedChart ? arrangement.confidence : hasVideo ? "Analysing" : arrangement.confidence}</b></div>
              <div className="confidence-track"><span /></div>
              <p>{hasGeneratedChart ? "Generated locally from the video audio. Treat it as a first pass and edit anything that sounds wrong." : hasVideo ? "The local analyser is reading the video audio. The generated chart will appear here when it finishes." : "Editable preview chart. Paste a YouTube link to start an actual song analysis."}</p>
            </div>
          </aside>

          <article className="chart-panel">
            <div className="chart-toolbar">
              <div className="instrument-switch" role="group" aria-label="Instrument">
                {["Ukulele", "Piano"].map((name) => (
                  <button key={name} type="button" className={instrument === name ? "active" : ""} onClick={() => setInstrument(name)}>{name}</button>
                ))}
              </div>
              <div className="toolbar-actions">
                <button type="button" className="icon-button" onClick={() => setTransposition((value) => value - 1)} aria-label="Transpose down"><Icon>♭</Icon></button>
                <span className="transpose-label">{transposition === 0 ? "Original key" : `${transposition > 0 ? "+" : ""}${transposition} semitone${Math.abs(transposition) === 1 ? "" : "s"}`}</span>
                <button type="button" className="icon-button" onClick={() => setTransposition((value) => value + 1)} aria-label="Transpose up"><Icon>♯</Icon></button>
                <span className="toolbar-divider" />
                <button type="button" className={`outline-button ${editMode ? "is-editing" : ""}`} onClick={() => setEditMode((value) => !value)}><Icon>✎</Icon> {editMode ? "Done" : "Edit"}</button>
                <button type="button" className="outline-button" onClick={copyChart}><Icon>⧉</Icon> Copy</button>
              </div>
            </div>
            
            {arrangement.progression && (
              <div className="core-progression-bar">
                <span className="progression-label"><Icon>✦</Icon> Repeating Pattern:</span>
                <strong className="progression-sequence">
                  {arrangement.progression.split(" ➔ ").map((chord, i) => (
                    <span key={i} className="progression-chord">
                      {chord.split(" ").map(part => transposeChord(part, transposition)).join(" ")}
                      {i < arrangement.progression.split(" ➔ ").length - 1 && <span className="progression-arrow"> ➔ </span>}
                    </span>
                  ))}
                </strong>
              </div>
            )}

            <div className="chart-heading">
              <div>
                <p className="section-kicker">{instrument === "Piano" ? "Piano chord guide · hands coming next" : "Ukulele arrangement"}</p>
                <h3>Chord chart</h3>
              </div>
              <div className="beat-legend"><span className="beat-fill" /> One chord per bar <span className="bar-line" /> 4/4 time</div>
            </div>

            {hasVideo && !hasGeneratedChart ? <div className="analysis-pending">
              <span className="analysis-icon"><Icon>◌</Icon></span>
              <div><strong>{status === "loading" ? "Listening for chords…" : "Video connected. Ready to analyse."}</strong><p>{status === "loading" ? "Downloading temporary audio and building an automatic chord draft. Longer videos can take a little while." : "Press “Make my chart” to generate a local chord draft from this video."}</p></div>
            </div> : <div className={`chart-content ${editMode ? "editing" : ""}`}>
              <div className="chord-timeline">
                {arrangement.timing && arrangement.timing.map((event, eventIndex) => {
                  const isActive = eventIndex === activeEventIndex;
                  return (
                    <div className={`chord-block ${isActive ? "active" : ""}`} key={eventIndex}>
                      {editMode ? (
                        <input
                          className="chord-editor"
                          value={event.chord}
                          onChange={(e) => updateChord(eventIndex, e.target.value)}
                          aria-label={`Edit chord`}
                        />
                      ) : (
                        <strong className="chord-display">
                          {transposeChord(event.chord, transposition)}
                        </strong>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>}

            <div className="practice-strip">
              <button type="button" className="play-button" onClick={() => showToast("Practice playback is queued for P3.")} aria-label="Play chart"><Icon>▶</Icon></button>
              <div><strong>Practice mode</strong><span>Loop sections, slow it down, and play along.</span></div>
              <button type="button" className="ghost-button" onClick={() => showToast("Practice mode is on the roadmap.")}>Set loop <Icon>→</Icon></button>
            </div>
          </article>
        </section>
      )}

      {toast && <div className="toast" role="status">{toast}</div>}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
