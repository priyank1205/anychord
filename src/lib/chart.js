// Lays a chord timeline out as bars and beats, the way a lead sheet does.
//
// Input: the analyser's `timing` (chords with start/end seconds) plus its beat
// grid (`beats`, `beats_per_bar`, `first_downbeat`). Output: bars, each split
// into segments proportional to how long each chord lasts inside that bar.

const EPSILON = 0.02;

function beatGrid(arrangement, end) {
  const beats = arrangement.beats?.length ? [...arrangement.beats] : [];
  const period = arrangement.tempo ? 60 / arrangement.tempo : 0.6;
  if (!beats.length) {
    for (let t = 0; t < end; t += period) beats.push(t);
  }
  return { beats, period };
}

export function buildBars(events, arrangement) {
  if (!events.length) return [];
  const end = events[events.length - 1].end;
  const { beats, period } = beatGrid(arrangement, end);
  const perBar = arrangement.beats_per_bar || 4;
  const first = Math.min(arrangement.first_downbeat ?? 0, beats.length - 1);
  const beatEnd = (i) => (i + 1 < beats.length ? beats[i + 1] : Math.max(end, beats[i] + period));

  // Group beat indices into bars; beats before the first downbeat form a pickup bar.
  const groups = [];
  if (first > 0) groups.push({ from: 0, to: first, pickup: true });
  for (let i = first; i < beats.length; i += perBar) groups.push({ from: i, to: Math.min(i + perBar, beats.length) });

  let eventIndex = 0;
  return groups.map((group, barIndex) => {
    const start = beats[group.from];
    const stop = beatEnd(group.to - 1);
    const segments = [];
    while (eventIndex < events.length && events[eventIndex].end <= start + EPSILON) eventIndex++;
    for (let i = eventIndex; i < events.length && events[i].start < stop - EPSILON; i++) {
      const event = events[i];
      const from = Math.max(event.start, start);
      const to = Math.min(event.end, stop);
      if (to - from < EPSILON) continue;
      segments.push({ event, from, to, isStart: event.start >= start - EPSILON, weight: to - from });
    }
    return {
      index: barIndex,
      number: group.pickup ? 0 : barIndex + (first > 0 ? 0 : 1),
      pickup: Boolean(group.pickup),
      start,
      end: stop,
      beats: Array.from({ length: group.to - group.from }, (_, k) => ({ start: beats[group.from + k], end: beatEnd(group.from + k) })),
      segments,
    };
  });
}

// Bars -> rows of `perRow` bars; the pickup bar shares the first row.
export function toRows(bars, perRow) {
  const rows = [];
  let row = [];
  for (const bar of bars) {
    row.push(bar);
    const full = row.filter((b) => !b.pickup).length >= perRow;
    if (full) {
      rows.push(row);
      row = [];
    }
  }
  if (row.length) rows.push(row);
  return rows.map((bars, index) => ({ index, bars, start: bars[0].start, end: bars[bars.length - 1].end }));
}

// Index of the item whose [start, end) contains t (items sorted by start).
export function findAt(items, t) {
  let lo = 0;
  let hi = items.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (t < items[mid].start) hi = mid - 1;
    else if (t >= items[mid].end) lo = mid + 1;
    else return mid;
  }
  return -1;
}
