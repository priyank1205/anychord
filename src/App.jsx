import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AnalysisProgress from "./components/AnalysisProgress";
import ChordEditor from "./components/ChordEditor";
import ChordGrid from "./components/ChordGrid";
import ChordName from "./components/ChordName";
import ChordSheet from "./components/ChordSheet";
import Icon from "./components/Icon";
import Landing, { LinkForm } from "./components/Landing";
import PlayerPanel from "./components/PlayerPanel";
import Toolbar from "./components/Toolbar";
import { useMediaQuery, useStoredState } from "./hooks/useAppState";
import { useYouTubePlayer } from "./hooks/useYouTubePlayer";
import { buildBars, findAt, toRows } from "./lib/chart";
import { formatTime, keyAt, simplifyChord, suggestCapo, transposeChord, transposeKey } from "./lib/music";
import { youtubeVideoId } from "./lib/trackInput";

const API = "http://127.0.0.1:8000";
const INSTRUMENTS = ["ukulele", "guitar", "piano"];

// Simple view: every chord as the triad you'd strum, repeats merged.
function simplifyTimeline(events) {
  const merged = [];
  for (const event of events) {
    const chord = simplifyChord(event.chord);
    const last = merged[merged.length - 1];
    if (last && last.chord === chord) {
      last.end = event.end;
      last.confidence = Math.min(last.confidence ?? 1, event.confidence ?? 1);
    } else {
      const alternative = event.alternative && simplifyChord(event.alternative) !== chord ? simplifyChord(event.alternative) : undefined;
      merged.push({ ...event, chord, alternative });
    }
  }
  return merged;
}

// Number of beats from `time` up to (and including) the beat at `until`.
function beatsBetween(beats, time, until) {
  let count = 0;
  for (const beat of beats) {
    if (beat > time + 0.02 && beat <= until + 0.05) count += 1;
  }
  return count;
}

function isTyping(target) {
  return target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
}

export default function App() {
  const [link, setLink] = useState("");
  const [phase, setPhase] = useState("idle"); // idle | loading | ready | error
  const [inputError, setInputError] = useState("");
  const [arrangement, setArrangement] = useState(null);
  const [videoId, setVideoId] = useState(null);
  const [analyzer, setAnalyzer] = useState(null);
  const [instrument, setInstrument] = useStoredState("anychords.instrument-choice", "ukulele", INSTRUMENTS);
  const [detail, setDetail] = useStoredState("anychords.detail", "full", ["full", "simple"]);
  const [sheetState, setSheetState] = useStoredState("anychords.sheet", "open", ["open", "closed"]);
  const [sensitivity, setSensitivity] = useState("normal");
  const [recharting, setRecharting] = useState(false);
  const [transposition, setTransposition] = useState(0);
  const [capo, setCapo] = useState(0);
  const [editMode, setEditMode] = useState(false);
  const [editing, setEditing] = useState(null);
  const [loopRow, setLoopRow] = useState(null);
  const [position, setPosition] = useState({
    event: -1,
    bar: -1,
    beat: -1,
    toNext: null,
  });
  const [toast, setToast] = useState(null);
  const narrow = useMediaQuery("(max-width: 760px)");
  const [playerVisible, setPlayerVisible] = useState(true);

  const timeRef = useRef(null);
  const barRefs = useRef({});
  const lastUserScroll = useRef(0);
  const frameRef = useRef(() => {});

  const player = useYouTubePlayer(videoId, (time) => frameRef.current(time));

  // ---- Server ------------------------------------------------------------
  useEffect(() => {
    fetch(`${API}/api/health`)
      .then((response) => response.json())
      .then(setAnalyzer)
      .catch(() => setAnalyzer({ offline: true }));
  }, []);

  const showToast = useCallback((message, tone = "neutral") => {
    setToast({ message, tone, id: Date.now() });
  }, []);
  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 2800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const requestChart = useCallback(async (url, mode) => {
    const response = await fetch(`${API}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ youtube_url: url, sensitivity: mode }),
    }).catch(() => {
      throw new Error("Can’t reach the analyser. Start AnyChords with npm start, then try again.");
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The chart couldn’t be made.");
    setAnalyzer({
      analyzer_version: result.analyzer_version,
      restart_required: result.restart_required,
    });
    return result;
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    const id = youtubeVideoId(link);
    if (!id) {
      setInputError("That doesn’t look like a YouTube link. Try one like youtube.com/watch?v=…");
      return;
    }
    setInputError("");
    setVideoId(id);
    setArrangement(null);
    setPhase("loading");
    setTransposition(0);
    setCapo(0);
    setEditMode(false);
    setLoopRow(null);
    setPosition({ event: -1, bar: -1, beat: -1, toNext: null });
    try {
      setArrangement(await requestChart(link, sensitivity));
      setPhase("ready");
    } catch (error) {
      setInputError(error.message);
      setPhase("error");
    }
  }

  async function changeSensitivity(mode) {
    if (mode === sensitivity || recharting) return;
    setSensitivity(mode);
    if (phase !== "ready") return;
    setRecharting(true);
    try {
      setArrangement(await requestChart(link, mode));
      showToast(mode === "sensitive" ? "Catching fast chord changes" : "Showing steady chord changes");
    } catch (error) {
      setSensitivity(sensitivity);
      showToast(error.message, "warn");
    } finally {
      setRecharting(false);
    }
  }

  // ---- Chart model ---------------------------------------------------------
  const simpleView = detail === "simple" && !editMode;
  const events = useMemo(() => {
    const timing = (arrangement?.timing ?? []).map((event, index) => ({
      ...event,
      index,
    }));
    return simpleView ? simplifyTimeline(timing) : timing;
  }, [arrangement, simpleView]);
  const bars = useMemo(() => (arrangement ? buildBars(events, arrangement) : []), [events, arrangement]);
  const perRow = narrow ? 2 : 4;
  const rows = useMemo(() => toRows(bars, perRow), [bars, perRow]);
  const capoUsed = instrument === "guitar" ? capo : 0;
  const offset = transposition - capoUsed;
  const display = useCallback(
    (chord, time = 0) => {
      if (!chord) return chord;
      const base = simpleView ? simplifyChord(chord) : chord;
      return transposeChord(base, offset, transposeKey(keyAt(time, arrangement ?? {}), offset));
    },
    [simpleView, offset, arrangement],
  );
  const shownKey = arrangement ? transposeKey(arrangement.key, transposition) : "";

  // Every chord in the song as shown (transposed, capo, simple), in the order
  // it first appears, with how often it is played.
  const songChords = useMemo(() => {
    const seen = new Map();
    for (const event of events) {
      if (event.chord === "N.C.") continue;
      const name = display(event.chord, event.start);
      const entry = seen.get(name) ?? { name, count: 0 };
      entry.count += 1;
      seen.set(name, entry);
    }
    return [...seen.values()];
  }, [events, display]);
  const hear = useCallback((chord) => import("./lib/audio").then((audio) => audio.playChordSound(chord, instrument)), [instrument]);
  const shapesKey = arrangement && capoUsed ? transposeKey(arrangement.key, offset) : null;
  const capoHint = useMemo(
    () => (arrangement && instrument === "guitar" ? suggestCapo(arrangement.timing, transposeKey(arrangement.key, transposition)).capo : 0),
    [arrangement, instrument, transposition],
  );
  const rowOfBar = useMemo(() => {
    const map = {};
    rows.forEach((row) => row.bars.forEach((bar) => (map[bar.index] = row.index)));
    return map;
  }, [rows]);
  const loopRange = loopRow !== null ? rows[loopRow] : null;

  // ---- Playback sync (runs every frame while playing) -----------------------
  frameRef.current = (time) => {
    if (timeRef.current) timeRef.current.textContent = formatTime(time);
    if (loopRange && time >= loopRange.end - 0.04) {
      player.seek(loopRange.start);
      return;
    }
    const eventIndex = findAt(events, time);
    const barIndex = findAt(bars, time);
    const beatIndex = barIndex >= 0 ? findAt(bars[barIndex].beats, time) : -1;
    if (barIndex >= 0) {
      const bar = bars[barIndex];
      barRefs.current[barIndex]?.style.setProperty("--p", String((time - bar.start) / (bar.end - bar.start)));
    }
    const next = events[eventIndex + 1];
    const toNext = next && arrangement?.beats ? beatsBetween(arrangement.beats, time, next.start) : null;
    if (eventIndex !== position.event || barIndex !== position.bar || beatIndex !== position.beat || toNext !== position.toNext) {
      setPosition({
        event: eventIndex,
        bar: barIndex,
        beat: beatIndex,
        toNext,
      });
    }
  };

  // Keep the playing line in view, unless the reader scrolled away recently.
  const activeRow = position.bar >= 0 ? rowOfBar[position.bar] : -1;
  useEffect(() => {
    if (!player.playing || activeRow < 0 || Date.now() - lastUserScroll.current < 4000) return;
    const node = document.querySelector(`[data-row="${activeRow}"]`);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    node?.scrollIntoView({
      block: "center",
      behavior: reduce ? "auto" : "smooth",
    });
  }, [activeRow, player.playing]);
  useEffect(() => {
    const mark = () => (lastUserScroll.current = Date.now());
    window.addEventListener("wheel", mark, { passive: true });
    window.addEventListener("touchmove", mark, { passive: true });
    return () => {
      window.removeEventListener("wheel", mark);
      window.removeEventListener("touchmove", mark);
    };
  }, []);

  const seekTo = useCallback(
    (time) => {
      lastUserScroll.current = 0;
      player.seek(time);
      frameRef.current(time);
      if (player.ready && !player.playing) player.play();
    },
    [player],
  );

  const stepChord = useCallback(
    (direction) => {
      if (!events.length) return;
      const time = player.currentTime();
      const index = Math.max(0, findAt(events, time));
      if (direction < 0 && events[index] && time - events[index].start > 1.2) return seekTo(events[index].start);
      const target = events[Math.min(events.length - 1, Math.max(0, index + direction))];
      if (target) seekTo(target.start);
    },
    [events, player, seekTo],
  );

  const toggleLoop = useCallback(() => {
    if (loopRow !== null) {
      setLoopRow(null);
      return;
    }
    const row = activeRow >= 0 ? activeRow : 0;
    setLoopRow(row);
    showToast(`Looping line ${row + 1}`);
  }, [loopRow, activeRow, showToast]);

  // ---- Actions ---------------------------------------------------------------
  function saveEdit(shown) {
    const event = editing;
    const original = offset ? transposeChord(shown, -offset, keyAt(event.start, arrangement)) : shown;
    setArrangement((current) => ({
      ...current,
      timing: current.timing.map((item, index) =>
        index === event.index ? { ...item, chord: original, confidence: 1, alternative: undefined } : item,
      ),
    }));
    setEditing(null);
    showToast(`Changed to ${shown}`);
  }

  function copyChart() {
    const text = rows
      .map(
        (row) =>
          `| ${row.bars
            .map(
              (bar) =>
                bar.segments
                  .filter((s, i) => s.isStart || i === 0)
                  .map((s) => display(s.event.chord, s.event.start))
                  .join(" ") || "%",
            )
            .join(" | ")} |`,
      )
      .join("\n");
    const header = `${arrangement.title} — ${shownKey}${shapesKey ? ` (capo ${capoUsed}, ${shapesKey} shapes)` : ""}, ${arrangement.tempo} BPM\n\n`;
    navigator.clipboard?.writeText(header + text).then(
      () => showToast("Chart copied"),
      () => showToast("Couldn’t copy. Select the chart instead.", "warn"),
    );
  }

  // ---- Keyboard ----------------------------------------------------------
  useEffect(() => {
    const onKey = (event) => {
      if (editing || isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey || phase !== "ready") return;
      const actions = {
        " ": () => player.toggle(),
        ArrowLeft: () => stepChord(-1),
        ArrowRight: () => stepChord(1),
        "-": () => setTransposition((value) => value - 1),
        "=": () => setTransposition((value) => value + 1),
        0: () => setTransposition(0),
        "+": () => setTransposition((value) => value + 1),
        s: () => setDetail((value) => (value === "simple" ? "full" : "simple")),
        e: () => setEditMode((value) => !value),
        l: () => toggleLoop(),
      };
      const action = actions[event.key];
      if (action) {
        event.preventDefault();
        action();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, phase, player, stepChord, toggleLoop, setDetail]);

  // ---- Views ---------------------------------------------------------------
  const inSong = phase === "loading" || phase === "ready" || (phase === "error" && Boolean(arrangement));
  const started = position.event >= 0;
  const now = started ? events[position.event] : null;
  const next = started ? events[position.event + 1] : events.find((event) => event.chord !== "N.C.");
  const confidence = typeof arrangement?.confidence === "number" ? Math.round(arrangement.confidence * 100) : null;
  const progression = arrangement?.progression
    ? arrangement.progression
        .split(" ➔ ")
        .map((chord) => display(chord))
        .filter((chord, i, all) => i === 0 || chord !== all[i - 1])
    : [];

  // The mini player takes over once Now / Next scrolls out of view.
  useEffect(() => {
    const node = document.querySelector(".shapes");
    if (!inSong || !node || typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver(([entry]) => setPlayerVisible(entry.intersectionRatio > 0.25), { threshold: [0, 0.25, 0.5] });
    observer.observe(node);
    return () => observer.disconnect();
  }, [inSong]);

  return (
    <div className="app">
      <header className="topbar">
        <button
          type="button"
          className="brand"
          onClick={() => {
            setPhase("idle");
            setVideoId(null);
            setArrangement(null);
          }}
          aria-label="AnyChords home"
        >
          <span className="brand__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path d="M5 17V7M10 17V4M15 17v-6M20 17V9" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
            </svg>
          </span>
          <span className="brand__label">AnyChords</span>
        </button>
        {inSong && (
          <div className="topbar__search">
            <LinkForm link={link} onLink={setLink} onSubmit={handleSubmit} busy={phase === "loading"} size="small" />
          </div>
        )}
      </header>

      {!inSong && <Landing link={link} onLink={setLink} onSubmit={handleSubmit} inputError={inputError} analyzer={analyzer} />}

      {inSong && (
        <main className="song">
          <aside className="song__side">
            <PlayerPanel
              player={player}
              now={phase === "ready" ? now : null}
              next={phase === "ready" ? next : null}
              started={started}
              duration={player.duration || events.at(-1)?.end || 0}
              beatsToNext={position.toNext}
              display={(chord) => display(chord, (now ?? next)?.start ?? 0)}
              instrument={instrument}
              onInstrument={setInstrument}
              loopOn={loopRow !== null}
              timeRef={timeRef}
              onPrev={() => stepChord(-1)}
              onNext={() => stepChord(1)}
              onToggleLoop={toggleLoop}
              onHear={hear}
            >
              {phase === "ready" && songChords.length > 0 && (
                <ChordSheet
                  chords={songChords}
                  active={started && now ? display(now.chord, now.start) : null}
                  instrument={instrument}
                  open={sheetState === "open"}
                  onToggle={() => setSheetState(sheetState === "open" ? "closed" : "open")}
                  onHear={hear}
                />
              )}
            </PlayerPanel>
          </aside>

          <section className="song__main" aria-label="Chord chart">
            <div className="song__heading">
              <div className="song__title">
                <p className="eyebrow">{phase === "loading" ? "Listening to the song…" : "Chord chart"}</p>
                <h1>{arrangement?.title || player.title || "Your song"}</h1>
                {arrangement && (
                  <div className="meta">
                    <span className="meta__item">
                      <strong>{shownKey}</strong>
                      {shapesKey && (
                        <em>
                          capo {capoUsed} · {shapesKey.replace(" major", "").replace(" minor", "m")} shapes
                        </em>
                      )}
                    </span>
                    <span className="meta__item">
                      <strong>{arrangement.tempo}</strong> BPM
                    </span>
                    <span className="meta__item">
                      <strong>{arrangement.meter}</strong>
                    </span>
                    {confidence !== null && (
                      <span className="meta__item" title="How sure the analyser is about the chords you’d strum">
                        <span className="confidence" style={{ "--c": confidence / 100 }} aria-hidden="true" />
                        <strong>{confidence}%</strong> sure
                      </span>
                    )}
                    {(arrangement.key_changes ?? []).map((change) => (
                      <span key={change.time} className="meta__item meta__item--soft">
                        → {transposeKey(change.key, transposition)} at {formatTime(change.time)}
                      </span>
                    ))}
                    {arrangement.artist && <span className="meta__item meta__item--soft">{arrangement.artist}</span>}
                  </div>
                )}
              </div>
              {phase === "ready" && (
                <div className="song__actions">
                  <button
                    type="button"
                    className={`ghost-btn ${editMode ? "is-on" : ""}`}
                    onClick={() => setEditMode(!editMode)}
                    aria-pressed={editMode}
                    aria-label={editMode ? "Done editing" : "Edit chords"}
                    title="Fix chords by hand (E)"
                  >
                    <Icon name={editMode ? "check" : "edit"} size={16} /> <span>{editMode ? "Done" : "Edit"}</span>
                  </button>
                  <button
                    type="button"
                    className="ghost-btn"
                    onClick={copyChart}
                    aria-label="Copy chart as text"
                    title="Copy the chart as text"
                  >
                    <Icon name="copy" size={16} /> <span>Copy</span>
                  </button>
                </div>
              )}
            </div>

            {analyzer?.restart_required && (
              <div className="notice notice--warn" role="alert">
                <Icon name="alert" size={18} />
                <span>
                  AnyChords was updated but the analyser is still running the old version. Press Ctrl+C in the terminal, run{" "}
                  <code>npm start</code>, then make the chart again.
                </span>
              </div>
            )}
            {phase === "ready" && sensitivity === "normal" && (arrangement.quick_changes_hint ?? 0) >= 3 && (
              <div className="notice">
                <Icon name="sparkle" size={18} />
                <span>
                  <strong>Catch fast changes</strong> finds {arrangement.quick_changes_hint} more chord changes in this song, ones that last
                  only a beat or two.
                </span>
                <button type="button" className="ghost-btn" onClick={() => changeSensitivity("sensitive")} disabled={recharting}>
                  Show them <Icon name="arrow" size={16} />
                </button>
              </div>
            )}

            {arrangement && (
              <Toolbar
                instrument={instrument}
                detail={detail}
                onDetail={setDetail}
                transposition={transposition}
                onTranspose={setTransposition}
                shownKey={shownKey || "Key"}
                originalKey={arrangement.key}
                capo={capo}
                onCapo={setCapo}
                suggestedCapo={capoHint}
                sensitivity={sensitivity}
                onSensitivity={changeSensitivity}
                recharting={recharting}
              />
            )}

            {progression.length > 1 && (
              <div className="progression" aria-label="Main progression">
                <span className="progression__label">Main progression</span>
                <ol>
                  {progression.map((chord, i) => (
                    <li key={i}>
                      <ChordName chord={chord} />
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {editMode && (
              <p className="edit-hint">
                <Icon name="edit" size={16} /> Tap a chord to change it. Changes stay until you load another song.
              </p>
            )}

            {phase === "loading" ? (
              <AnalysisProgress />
            ) : (
              <ChordGrid
                rows={rows}
                perRow={perRow}
                beatsPerBar={arrangement?.beats_per_bar || 4}
                display={display}
                activeEvent={events[position.event]}
                activeBar={position.bar}
                activeBeat={position.beat}
                loopRow={loopRow}
                editMode={editMode}
                barRefs={barRefs}
                onSeek={seekTo}
                onEdit={setEditing}
              />
            )}

            {phase === "ready" && (
              <footer className="song__footer">
                <span>
                  {sensitivity === "sensitive" ? "Catching fast changes" : "Steady"} · analyser {arrangement.analyzer_version ?? "unknown"}
                </span>
                <span className="shortcuts" aria-label="Keyboard shortcuts">
                  <Icon name="keyboard" size={16} />
                  <kbd>Space</kbd> play <kbd>←</kbd>
                  <kbd>→</kbd> chords <kbd>L</kbd> loop <kbd>S</kbd> simple <kbd>E</kbd> edit <kbd>−</kbd>
                  <kbd>+</kbd> key <kbd>0</kbd> reset key
                </span>
              </footer>
            )}
          </section>

          {phase === "ready" && (
            <div className={`minibar ${playerVisible ? "" : "is-shown"}`} aria-label="Now playing" aria-hidden={playerVisible}>
              <button
                type="button"
                className="play-btn play-btn--small"
                onClick={player.toggle}
                disabled={!player.ready}
                aria-label={player.playing ? "Pause" : "Play"}
                tabIndex={playerVisible ? -1 : 0}
              >
                <Icon name={player.playing ? "pause" : "play"} size={18} />
              </button>
              <div className="minibar__now">
                <span>Now</span>
                {started ? (
                  <ChordName chord={now ? display(now.chord, now.start) : "N.C."} />
                ) : (
                  <span className="chord-name chord-name--rest">Ready</span>
                )}
              </div>
              <div className="minibar__next">
                <span>{position.toNext ? `Next · in ${position.toNext}` : "Next"}</span>
                <ChordName chord={next ? display(next.chord, next.start) : "N.C."} />
              </div>
              <button
                type="button"
                className="minibar__speed"
                onClick={() => player.setRate(player.rate === 1 ? 0.75 : player.rate === 0.75 ? 0.5 : 1)}
                disabled={!player.ready}
                aria-label={`Speed ${player.rate}×, tap to change`}
                tabIndex={playerVisible ? -1 : 0}
              >
                {player.rate}×
              </button>
              <button
                type="button"
                className={`icon-btn ${loopRow !== null ? "is-on" : ""}`}
                onClick={toggleLoop}
                aria-pressed={loopRow !== null}
                aria-label={loopRow !== null ? "Stop looping" : "Loop this line"}
                tabIndex={playerVisible ? -1 : 0}
              >
                <Icon name="loop" />
              </button>
            </div>
          )}
        </main>
      )}

      {editing && (
        <ChordEditor
          event={editing}
          display={(chord) => display(chord, editing.start)}
          onSave={saveEdit}
          onClose={() => setEditing(null)}
        />
      )}

      {toast && (
        <div key={toast.id} className={`toast toast--${toast.tone}`} role="status">
          {toast.message}
        </div>
      )}
    </div>
  );
}
