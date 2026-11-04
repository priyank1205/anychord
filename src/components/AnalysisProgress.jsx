import { useEffect, useState } from "react";
import Icon from "./Icon";

// The analyser answers in one request, so stages advance on typical timings.
const STAGES = [
  ["Downloading the audio", 0],
  ["Finding the beat", 9],
  ["Naming the chords", 16],
];

export default function AnalysisProgress() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 250);
    return () => window.clearInterval(timer);
  }, []);
  const current = STAGES.reduce((index, [, at], i) => (elapsed >= at ? i : index), 0);
  return (
    <div className="progress" role="status" aria-live="polite">
      <ol className="progress__steps">
        {STAGES.map(([label], index) => (
          <li key={label} className={index < current ? "is-done" : index === current ? "is-now" : ""}>
            <span className="progress__mark">{index < current ? <Icon name="check" size={14} /> : <span />}</span>
            {label}
          </li>
        ))}
      </ol>
      <p className="progress__note">{Math.floor(elapsed)} s · usually under a minute. Longer videos take longer.</p>
      <div className="progress__skeleton" aria-hidden="true">
        {Array.from({ length: 12 }, (_, i) => (
          <span key={i} style={{ animationDelay: `${(i % 4) * 120}ms` }} />
        ))}
      </div>
    </div>
  );
}
