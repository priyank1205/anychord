import ChordDiagram from "./ChordDiagram";
import ChordName from "./ChordName";
import Icon from "./Icon";
import Segmented from "./Segmented";
import { formatTime } from "../lib/music";

const SPEEDS = [0.5, 0.75, 1];

function Countdown({ beats }) {
  if (beats == null) return null;
  const shown = Math.min(beats, 8);
  return (
    <span className="countdown" aria-label={`in ${beats} beat${beats === 1 ? "" : "s"}`}>
      {Array.from({ length: shown }, (_, i) => (
        <span key={i} />
      ))}
      <em>in {beats}</em>
    </span>
  );
}

export default function PlayerPanel({
  player,
  now,
  next,
  started,
  duration,
  beatsToNext,
  display,
  instrument,
  onInstrument,
  loopOn,
  timeRef,
  onPrev,
  onNext,
  onToggleLoop,
  onHear,
  compact = false,
  children,
}) {
  const nowChord = now ? display(now.chord) : null;
  const nextChord = next ? display(next.chord) : null;
  return (
    <section className="player" aria-label="Player">
      <div className="player__video">
        <div ref={player.hostRef} className="player__frame" />
        {!player.ready && <div className="player__placeholder" aria-hidden="true" />}
      </div>

      <div className="transport" role="group" aria-label="Playback">
        <button type="button" className="icon-btn" onClick={onPrev} aria-label="Previous chord" title="Previous chord (←)">
          <Icon name="prev" />
        </button>
        <button
          type="button"
          className="play-btn"
          onClick={player.toggle}
          disabled={!player.ready}
          aria-label={player.playing ? "Pause" : "Play"}
          title={player.playing ? "Pause (space)" : "Play (space)"}
        >
          <Icon name={player.playing ? "pause" : "play"} size={22} />
        </button>
        <button type="button" className="icon-btn" onClick={onNext} aria-label="Next chord" title="Next chord (→)">
          <Icon name="next" />
        </button>
        <span className="transport__time">
          <b ref={timeRef} style={{ fontWeight: "inherit" }}>
            0:00
          </b>
          <span> / {formatTime(duration)}</span>
        </span>
        <div className="transport__end">
          <div className="segmented segmented--small" role="group" aria-label="Speed">
            {SPEEDS.map((speed) => (
              <button
                key={speed}
                type="button"
                className={player.rate === speed ? "is-on" : ""}
                aria-pressed={player.rate === speed}
                onClick={() => player.setRate(speed)}
                disabled={!player.ready}
              >
                {speed === 1 ? "1×" : `${speed}×`}
              </button>
            ))}
          </div>
          <button
            type="button"
            className={`icon-btn ${loopOn ? "is-on" : ""}`}
            onClick={onToggleLoop}
            aria-pressed={loopOn}
            aria-label={loopOn ? "Stop looping this line" : "Loop this line"}
            title={loopOn ? "Stop looping (L)" : "Loop the current line (L)"}
          >
            <Icon name="loop" />
          </button>
        </div>
      </div>

      <div className="shapes">
        <div className="shapes__head">
          <span className="shapes__label">Chord shapes</span>
          <Segmented
            label="Show chord shapes for"
            size="small"
            value={instrument}
            onChange={onInstrument}
            options={[
              ["ukulele", "Ukulele"],
              ["guitar", "Guitar"],
              ["piano", "Piano"],
            ]}
          />
        </div>
        {compact ? null : !now && !next && !started ? (
          <div className="nownext">
            <p className="nownext__empty">Chords and finger shapes show up here once the chart is ready.</p>
          </div>
        ) : (
          <div className="nownext">
            <div className="nownext__now">
              <div className="nownext__label">
                Now
                {nowChord && nowChord !== "N.C." && (
                  <button
                    type="button"
                    className="hear-btn"
                    onClick={() => onHear(nowChord)}
                    aria-label={`Hear ${nowChord}`}
                    title="Hear it"
                  >
                    <Icon name="sound" size={16} />
                  </button>
                )}
              </div>
              {started || nowChord ? (
                <>
                  <ChordName chord={nowChord ?? "N.C."} className="nownext__chord" />
                  <ChordDiagram chord={nowChord} instrument={instrument} size={instrument === "piano" ? 168 : 112} />
                </>
              ) : (
                <>
                  <span className="nownext__chord chord-name chord-name--rest">Ready</span>
                  <p className="nownext__ready">Press play, or tap any chord in the chart to start there.</p>
                </>
              )}
            </div>
            <div className="nownext__next">
              <div className="nownext__label">
                Next <Countdown beats={beatsToNext} />
              </div>
              <ChordName chord={nextChord ?? "N.C."} className="nownext__chord nownext__chord--next" />
              <ChordDiagram chord={nextChord} instrument={instrument} size={instrument === "piano" ? 140 : 96} />
            </div>
          </div>
        )}
      </div>
      {!compact && children}
    </section>
  );
}
