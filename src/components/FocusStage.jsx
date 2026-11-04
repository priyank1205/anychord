import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import ChordDiagram from "./ChordDiagram";
import ChordName from "./ChordName";

// How many beats ahead the lane shows: enough for the next few chords at
// this song's typical chord length, within limits that keep names readable.
// One zoom per song, so the lane always moves at a steady speed.
function beatsShown(width, typicalBeats) {
  const [chords, min, max] = width >= 760 ? [6.5, 8, 40] : width >= 460 ? [5, 6, 30] : [3.5, 5, 18];
  return Math.min(max, Math.max(min, Math.round(typicalBeats * chords)));
}

// The last beat at or before `time`, so reduced motion steps instead of glides.
function beatFloor(beats, time) {
  let lo = 0;
  let hi = beats.length - 1;
  let found = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (beats[mid] <= time) {
      found = beats[mid];
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return found;
}

// Focus view: the chord playing now, big, and the next ones scrolling in from
// the right at the song's own speed. Each chord is as wide as it lasts, so its
// distance from the line shows how soon it comes.
//
// Only a window of chords around "now" is drawn, measured from the previous
// chord's start (`origin`), so the moving strip stays a few screens wide even
// in long songs. The strip moves by a transform set every frame through
// `frameRef`, not by re-rendering; after each render the transform is
// re-applied so the window and the position always change together.
export default function FocusStage({
  events,
  beats,
  beatsPerBar = 4,
  firstDownbeat = 0,
  tempo,
  display,
  instrument,
  nowIndex,
  started,
  beatInBar,
  toNext,
  frameRef,
  currentTime,
  onSeek,
}) {
  const laneRef = useRef(null);
  const trackRef = useRef(null);
  const [laneWidth, setLaneWidth] = useState(0);

  useLayoutEffect(() => {
    const lane = laneRef.current;
    if (!lane) return undefined;
    setLaneWidth(lane.clientWidth);
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => setLaneWidth(entry.contentRect.width));
    observer.observe(lane);
    return () => observer.disconnect();
  }, []);

  const end = events.length ? events[events.length - 1].end : 0;
  const beatSeconds = 60 / (tempo || 100);
  const beatTimes = useMemo(
    () => (beats?.length ? beats : Array.from({ length: Math.ceil(end / beatSeconds) + 1 }, (_, i) => i * beatSeconds)),
    [beats, end, beatSeconds],
  );
  const typicalBeats = useMemo(() => {
    const lengths = events
      .filter((event) => event.chord !== "N.C.")
      .map((event) => (event.end - event.start) / beatSeconds)
      .sort((a, b) => a - b);
    return lengths.length ? lengths[Math.floor(lengths.length / 2)] : 4;
  }, [events, beatSeconds]);
  const span = beatsShown(laneWidth || 800, typicalBeats);
  const pps = laneWidth ? laneWidth / (span * beatSeconds) : 0; // pixels per second

  // The window: from the previous chord to a few screens past the current one.
  const first = Math.max(0, nowIndex - 1);
  const origin = events[first]?.start ?? 0;
  const current = started ? events[nowIndex] : null;
  const horizon = (current ? current.end : origin) + 3 * span * beatSeconds;
  let last = first;
  while (last + 1 < events.length && events[last + 1].start < horizon) last += 1;
  const shown = events.slice(first, last + 1);
  const windowEnd = events[last]?.end ?? origin;
  const trackWidth = Math.ceil((windowEnd - origin) * pps);
  const windowBeats = beatTimes
    .map((time, i) => ({ time, bar: i >= firstDownbeat && (i - firstDownbeat) % beatsPerBar === 0 }))
    .filter(({ time }) => time >= origin && time <= windowEnd);

  // Latest window and scale, read by the per-frame update without re-rendering.
  const place = useRef(null);
  place.current = { origin, pps, beats: beatTimes };

  const applyRef = useRef(null);
  if (!applyRef.current) {
    const reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    applyRef.current = (time) => {
      const track = trackRef.current;
      const lane = laneRef.current;
      if (!track) return;
      if (lane && lane.scrollLeft) lane.scrollLeft = 0; // never let the browser scroll the lane itself
      const { origin: o, pps: p, beats: b } = place.current;
      const t = reduce ? beatFloor(b, time) : time;
      track.style.transform = `translate3d(${(-(t - o) * p).toFixed(1)}px, 0, 0)`;
    };
  }

  useEffect(() => {
    const apply = applyRef.current;
    frameRef.current = apply;
    return () => {
      if (frameRef.current === apply) frameRef.current = null;
    };
  }, [frameRef]);

  // After every render (new window, new size): line the strip up with the music again.
  useLayoutEffect(() => {
    applyRef.current(currentTime());
  });

  const nextIndex = events.findIndex((event, index) => index > nowIndex && event.chord !== "N.C.");
  const nowName = current ? display(current.chord, current.start) : null;
  const nextName = nextIndex >= 0 ? display(events[nextIndex].chord, events[nextIndex].start) : null;

  return (
    <section className={`stage ${instrument === "piano" ? "stage--piano" : ""}`} aria-label="Focus view">
      <div className="stage__now">
        <div className="stage__top">
          <span className="stage__label">Now</span>
          {started && beatInBar && (
            <span className="stage__beats" aria-label={`beat ${beatInBar.beat + 1} of ${beatInBar.count}`}>
              {Array.from({ length: beatInBar.count }, (_, i) => (
                <i key={i} className={i === beatInBar.beat ? "is-on" : ""} />
              ))}
            </span>
          )}
        </div>
        {started ? (
          <ChordName
            chord={nowName ?? "N.C."}
            className={`stage__chord ${nowName?.length > 7 ? "stage__chord--longer" : nowName?.length > 4 ? "stage__chord--long" : ""}`}
          />
        ) : (
          <span className="stage__chord chord-name chord-name--rest">Ready</span>
        )}
        {(!nowName || nowName === "N.C.") && (
          <p className="stage__hint">{started ? "No chord here." : "Press play, or tap a chord on the right to start there."}</p>
        )}
        <div className="stage__shapes">
          {nowName && nowName !== "N.C." && (
            <div className="stage__shape">
              <ChordDiagram chord={nowName} instrument={instrument} size={instrument === "piano" ? 190 : 120} />
            </div>
          )}
          {nextName && (
            <div className="stage__next" aria-label={`Next: ${nextName}`}>
              <span className="stage__next-label">
                Next <ChordName chord={nextName} />
              </span>
              <ChordDiagram chord={nextName} instrument={instrument} size={instrument === "piano" ? 120 : 70} />
            </div>
          )}
        </div>
      </div>

      <div className="lane" ref={laneRef}>
        <div className="lane__track" ref={trackRef} style={{ width: `${trackWidth}px` }}>
          <svg className="lane__beats" width={trackWidth} height="26" aria-hidden="true">
            {windowBeats.map(({ time, bar }) => {
              const x = Math.round((time - origin) * pps) + 0.5;
              return <line key={time} x1={x} x2={x} y1={bar ? 4 : 14} y2="26" className={bar ? "lane__bar" : "lane__beat"} />;
            })}
          </svg>
          {shown.map((event, offset) => {
            const index = first + offset;
            const name = display(event.chord, event.start);
            const rest = event.chord === "N.C.";
            const isNow = index === nowIndex;
            const isNext = index === nextIndex;
            const width = (event.end - event.start) * pps;
            const ahead = index - nowIndex;
            return (
              <button
                key={index}
                type="button"
                tabIndex={-1}
                className={["lane__block", isNow && "is-now", isNext && "is-next", rest && "is-rest"].filter(Boolean).join(" ")}
                style={{
                  left: `${(event.start - origin) * pps}px`,
                  width: `${width}px`,
                  "--fit": `${Math.floor(width / Math.max(2.4, name.length * 0.62))}px`,
                  opacity: isNow || isNext || ahead <= 1 ? 1 : Math.max(0.42, 1 - (ahead - 1) * 0.14),
                }}
                onMouseDown={(event) => event.preventDefault()} // no focus, so the browser never scrolls the lane to it
                onClick={() => onSeek(event.start)}
                aria-label={rest ? "Play from here (no chord)" : `Play from ${name}`}
              >
                {!isNow && !rest && (
                  <span className="lane__head">
                    <ChordName chord={name} className="lane__chord" />
                    {isNext && index === nowIndex + 1 && toNext && width >= 70 + name.length * 22 ? (
                      <span className="lane__in">in {toNext}</span>
                    ) : null}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
