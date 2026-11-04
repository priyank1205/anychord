import ChordDiagram from "./ChordDiagram";
import ChordName from "./ChordName";
import Icon from "./Icon";
import Segmented from "./Segmented";

// Every chord in the song with its shape, in the order they first appear,
// like the chord boxes at the top of a songbook page. The playing chord
// lights up; the rest stay neutral so the eye finds it.
export default function ChordSheet({ chords, active, instrument, onInstrument, open, onToggle, onHear }) {
  const piano = instrument === "piano";
  return (
    <section className={`sheet ${piano ? "sheet--piano" : ""}`} aria-labelledby="sheet-title">
      <div className="sheet__head">
        <h2 id="sheet-title">
          <button type="button" className="sheet__toggle" onClick={onToggle} aria-expanded={open} aria-controls="sheet-body">
            Chords in this song
            <span className="sheet__total">{chords.length}</span>
            <Icon name="chevron" size={16} className="sheet__chevron" />
          </button>
        </h2>
        {open && (
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
        )}
      </div>
      {open && (
        <ul id="sheet-body" className="sheet__grid">
          {chords.map(({ name, count }) => (
            <li key={name} className={`sheet__card ${name.length > 6 ? "sheet__card--long" : ""} ${name === active ? "is-active" : ""}`}>
              <div className="sheet__top">
                <ChordName chord={name} />
                <button type="button" className="hear-btn" onClick={() => onHear(name)} aria-label={`Hear ${name}`} title="Hear it">
                  <Icon name="sound" size={15} />
                </button>
              </div>
              <ChordDiagram chord={name} instrument={instrument} size={piano ? 132 : 84} />
              <span className="sheet__count" title={`Played ${count === 1 ? "once" : `${count} times`} in the song`}>
                {count === 1 ? "once" : `${count}×`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
