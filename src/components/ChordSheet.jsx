import ChordDiagram from "./ChordDiagram";
import ChordName from "./ChordName";
import Icon from "./Icon";

// Every chord in the song with its shape, in the order they first appear,
// like the chord boxes at the top of a songbook page. Sits under Now / Next
// in the side panel. The playing chord lights up; tap any box to hear it.
export default function ChordSheet({ chords, active, instrument, open, onToggle, onHear }) {
  const piano = instrument === "piano";
  return (
    <section className={`sheet ${piano ? "sheet--piano" : ""} ${open ? "is-open" : ""}`} aria-labelledby="sheet-title">
      <div className="sheet__head">
        <h2 id="sheet-title">
          <button type="button" className="sheet__toggle" onClick={onToggle} aria-expanded={open} aria-controls="sheet-body">
            Chords in this song
            <span className="sheet__total">{chords.length}</span>
            <Icon name="chevron" size={16} className="sheet__chevron" />
          </button>
        </h2>
        {open && <span className="sheet__hint">Tap one to hear it</span>}
      </div>
      {open && (
        <ul id="sheet-body" className="sheet__grid">
          {chords.map(({ name, count }) => (
            <li key={name}>
              <button
                type="button"
                className={`sheet__card ${name.length > 5 ? "sheet__card--long" : ""} ${name === active ? "is-active" : ""}`}
                onClick={() => onHear(name)}
                aria-label={`${name}, played ${count === 1 ? "once" : `${count} times`}. Hear it`}
                title={`Hear ${name} · played ${count === 1 ? "once" : `${count} times`}`}
              >
                <span className="sheet__top">
                  <ChordName chord={name} />
                  <span className="sheet__count" aria-hidden="true">
                    {count}×
                  </span>
                </span>
                <ChordDiagram chord={name} instrument={instrument} size={piano ? 104 : 66} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
