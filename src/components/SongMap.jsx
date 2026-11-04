import { useEffect, useRef } from "react";
import ChordGrid from "./ChordGrid";

// The whole song, small: every bar and chord, the playing bar lit and what's
// been played dimmed. It keeps the playing line at the top of its box, so
// everything below is what's coming. Tap any chord to play from there.
export default function SongMap({ rows, perRow, beatsPerBar, display, activeEvent, activeBar, activeBeat, barRefs, onSeek }) {
  const boxRef = useRef(null);
  const touched = useRef(0);
  const activeRow = rows.findIndex((row) => row.bars.some((bar) => bar.index === activeBar));
  const total = rows.reduce((count, row) => count + row.bars.filter((bar) => !bar.pickup).length, 0);
  const current = rows[activeRow]?.bars.find((bar) => bar.index === activeBar)?.number;

  // Follow the music inside the box only (never the page), unless the person
  // has just scrolled the map themselves.
  useEffect(() => {
    const box = boxRef.current;
    if (!box || activeRow < 0 || Date.now() - touched.current < 4000) return;
    const row = box.querySelector(`[data-row="${activeRow}"]`);
    if (!row) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    box.scrollTo({ top: Math.max(0, row.offsetTop - 4), behavior: reduce ? "auto" : "smooth" });
  }, [activeRow]);

  const mark = () => {
    touched.current = Date.now();
  };

  return (
    <section className="map" aria-label="Whole song">
      <div className="map__head">
        <span className="map__title">Whole song</span>
        <span>{current ? `Bar ${current} of ${total}` : `${total} bars · tap a chord to start there`}</span>
      </div>
      <div className="map__box" ref={boxRef} onWheel={mark} onTouchMove={mark}>
        <ChordGrid
          variant="map"
          rows={rows}
          perRow={perRow}
          beatsPerBar={beatsPerBar}
          display={display}
          activeEvent={activeEvent}
          activeBar={activeBar}
          activeBeat={activeBeat}
          barRefs={barRefs}
          onSeek={onSeek}
        />
      </div>
    </section>
  );
}
