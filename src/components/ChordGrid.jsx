import ChordName from "./ChordName";

const LOW_CONFIDENCE = 0.6;

// A lead-sheet style grid: rows of bars, each bar split into chord segments
// whose widths follow how long each chord sounds. Beat dots sit under every
// bar; the playing bar gets a moving playhead (set imperatively via --p).
export default function ChordGrid({
  rows,
  perRow,
  beatsPerBar = 4,
  display,
  activeEvent,
  activeBar,
  activeBeat,
  loopRow,
  editMode,
  interactive = true,
  barRefs,
  onSeek,
  onEdit,
}) {
  return (
    <div className={`grid ${editMode ? "grid--editing" : ""}`}>
      {rows.map((row) => {
        const fill = Math.max(0, perRow - row.bars.filter((bar) => !bar.pickup).length);
        const columns = row.bars.map((bar) => `${Math.min(1, bar.beats.length / beatsPerBar)}fr`);
        if (fill) columns.push(`${fill}fr`);
        const firstNumber = row.bars.find((bar) => !bar.pickup)?.number;
        return (
          <div key={row.index} className={`grid__row ${loopRow === row.index ? "is-looped" : ""}`} data-row={row.index}>
            <span className="grid__number" aria-hidden="true">
              {firstNumber || ""}
            </span>
            <div className="grid__bars" style={{ gridTemplateColumns: columns.join(" ") }}>
              {row.bars.map((bar, barPosition) => {
                const isActiveBar = activeBar === bar.index;
                return (
                  <div
                    key={bar.index}
                    ref={barRefs ? (node) => (barRefs.current[bar.index] = node) : undefined}
                    className={`bar ${bar.pickup ? "bar--pickup" : ""} ${isActiveBar ? "is-active" : ""}`}
                  >
                    <div className="bar__segments">
                      {bar.segments.map((segment, segmentIndex) => {
                        const { event } = segment;
                        const chord = display(event.chord);
                        const isActive = activeEvent === event;
                        const held = !segment.isStart;
                        const showHeld = held && barPosition === 0 && segmentIndex === 0;
                        const uncertain = segment.isStart && typeof event.confidence === "number" && event.confidence < LOW_CONFIDENCE;
                        const share = segment.weight / (bar.end - bar.start);
                        const alternative = event.alternative ? display(event.alternative) : null;
                        const label = held ? `${chord} continues` : `${chord}${uncertain ? ", unsure" : ""}`;
                        const Tag = interactive ? "button" : "div";
                        return (
                          <Tag
                            key={segmentIndex}
                            type={interactive ? "button" : undefined}
                            className={[
                              "seg",
                              isActive && "is-active",
                              held && "seg--held",
                              uncertain && "seg--unsure",
                              share < 0.3 && "seg--tight",
                              chord === "N.C." && "seg--rest",
                            ]
                              .filter(Boolean)
                              .join(" ")}
                            style={{ flexGrow: segment.weight }}
                            onClick={
                              interactive
                                ? () => (editMode && segment.isStart ? onEdit?.(event) : onSeek?.(held ? segment.from : event.start))
                                : undefined
                            }
                            aria-label={interactive ? (editMode && !held ? `Edit ${chord}` : `Play from ${label}`) : undefined}
                            title={uncertain ? `Not sure about this one${alternative ? ` (could be ${alternative})` : ""}` : undefined}
                          >
                            {(!held || showHeld) && <ChordName chord={chord} />}
                            {uncertain && <span className="seg__flag" aria-hidden="true" />}
                          </Tag>
                        );
                      })}
                    </div>
                    <div className="bar__beats" aria-hidden="true">
                      {bar.beats.map((_, beat) => (
                        <span key={beat} className={isActiveBar && activeBeat === beat ? "is-on" : ""} />
                      ))}
                    </div>
                    {isActiveBar && <span className="bar__playhead" aria-hidden="true" />}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
