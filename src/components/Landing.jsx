import { useEffect, useRef, useState } from "react";
import ChordGrid from "./ChordGrid";
import Icon from "./Icon";
import ProblemCard, { SIGN_IN_BROWSERS } from "./ProblemCard";
import { buildBars, findAt, toRows } from "../lib/chart";
import { DEMO } from "../data/demo";

const demoBars = buildBars(DEMO.timing, DEMO);
const demoRows = toRows(demoBars, 4);
const demoLength = DEMO.timing[DEMO.timing.length - 1].end;

// The example chart plays itself, so the page shows what a chart does.
function useDemoPlayback(barRefs) {
  const [position, setPosition] = useState({ event: 4, bar: 3, beat: 0 });
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    const started = performance.now();
    let frame = 0;
    let last = "";
    const tick = (now) => {
      const time = ((now - started) / 1000 + 0.01) % demoLength;
      const bar = findAt(demoBars, time);
      const beat = bar >= 0 ? findAt(demoBars[bar].beats, time) : -1;
      const event = findAt(DEMO.timing, time);
      if (bar >= 0)
        barRefs.current[bar]?.style.setProperty("--p", String((time - demoBars[bar].start) / (demoBars[bar].end - demoBars[bar].start)));
      const key = `${event}:${bar}:${beat}`;
      if (key !== last) {
        last = key;
        setPosition({ event, bar, beat });
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [barRefs]);
  return position;
}

function Preview() {
  const barRefs = useRef({});
  const position = useDemoPlayback(barRefs);
  return (
    <section className="preview" aria-label="Example chart">
      <div className="preview__frame">
        <div className="preview__head">
          <span className="eq" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span className="preview__title">
            <strong>Example chart</strong> · F major · 94 BPM · 4/4
          </span>
        </div>
        <ChordGrid
          rows={demoRows}
          perRow={4}
          display={(chord) => chord}
          activeEvent={DEMO.timing[position.event]}
          activeBar={position.bar}
          activeBeat={position.beat}
          interactive={false}
          barRefs={barRefs}
        />
      </div>
    </section>
  );
}

function AnalyzerStatus({ analyzer }) {
  if (!analyzer) return <span className="status-pill">Checking the analyser…</span>;
  if (analyzer.offline) {
    return (
      <span className="status-pill status-pill--warn">
        <span className="status-pill__dot" /> Analyser isn’t running. Start it with <code>npm start</code>
      </span>
    );
  }
  return (
    <span className="status-pill status-pill--ok">
      <span className="status-pill__dot" /> Analyser ready · runs on this computer
    </span>
  );
}

export function LinkForm({ link, onLink, onSubmit, busy, size = "large", autoFocus }) {
  return (
    <form className={`link-form link-form--${size}`} onSubmit={onSubmit}>
      <Icon name="link" size={size === "large" ? 20 : 18} className="link-form__icon" />
      <label className="visually-hidden" htmlFor={`link-${size}`}>
        YouTube link
      </label>
      <input
        id={`link-${size}`}
        value={link}
        onChange={(event) => onLink(event.target.value)}
        placeholder="Paste a YouTube link"
        autoComplete="off"
        spellCheck={false}
        inputMode="url"
        autoFocus={autoFocus}
      />
      <button type="submit" className="primary-btn" disabled={busy}>
        {busy ? "Listening…" : size === "large" ? "Get chords" : "Go"}
        {!busy && <Icon name="arrow" size={18} />}
      </button>
    </form>
  );
}

export default function Landing({ link, onLink, onSubmit, problem, analyzer, browser, onUseBrowser, onForgetBrowser, onRetry }) {
  const browserName = SIGN_IN_BROWSERS.find(([value]) => value === browser)?.[1];
  return (
    <main className="landing">
      <section className="hero">
        <AnalyzerStatus analyzer={analyzer} />
        <h1>
          Play along with <em>any song.</em>
        </h1>
        <p className="hero__lede">
          Paste a YouTube link. AnyChords listens to the audio and writes a chord chart that follows the music, beat by beat.
        </p>
        <LinkForm link={link} onLink={onLink} onSubmit={onSubmit} autoFocus />
        {problem && <ProblemCard problem={problem} browser={browser} onUseBrowser={onUseBrowser} onRetry={onRetry} />}
        {!problem && browserName && (
          <p className="sign-in-note">
            If YouTube blocks a download, AnyChords uses your {browserName} YouTube sign-in.{" "}
            <button type="button" className="link-btn" onClick={onForgetBrowser}>
              Stop
            </button>
          </p>
        )}
      </section>

      <Preview />

      <section className="features" aria-label="What you get">
        <article>
          <Icon name="wave" size={22} />
          <h2>Follows the music</h2>
          <p>Chords sit in real bars and beats, and light up as the video plays. Tap any chord to jump there.</p>
        </article>
        <article>
          <Icon name="sparkle" size={22} />
          <h2>Every chord type</h2>
          <p>7ths, sus, add9, slash chords and more, or switch to Simple for plain triads.</p>
        </article>
        <article>
          <Icon name="loop" size={22} />
          <h2>Made for practice</h2>
          <p>Slow it down, loop a line, transpose, or use a capo. Diagrams for guitar, ukulele and piano.</p>
        </article>
      </section>
    </main>
  );
}
