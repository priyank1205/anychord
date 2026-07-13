import React from 'react';
import ukeDb from '@tombatossals/chords-db/lib/ukulele.json';

const parseChordName = (chordString) => {
  if (!chordString) return null;
  const base = chordString.split('/')[0].trim();
  const match = base.match(/^([A-G][#b]?)(.*)$/);
  if (!match) return null;

  let root = match[1];
  let suffixStr = match[2].trim();

  const enharmonics = {
    'A#': 'Bb',
    'C#': 'Db',
    'D#': 'Eb',
    'F#': 'Gb',
    'G#': 'Ab'
  };
  root = enharmonics[root] || root;

  let suffix = 'major';
  if (suffixStr === 'm' || suffixStr === 'min') suffix = 'minor';
  else if (suffixStr === 'm7' || suffixStr === 'min7') suffix = 'm7';
  else if (suffixStr === 'maj7') suffix = 'maj7';
  else if (suffixStr === '7') suffix = '7';
  else if (suffixStr === 'sus4') suffix = 'sus4';
  else if (suffixStr === 'sus2') suffix = 'sus2';
  else if (suffixStr === 'dim') suffix = 'dim';
  else if (suffixStr === 'aug') suffix = 'aug';
  else if (suffixStr !== '') suffix = suffixStr;

  return { root, suffix };
};

export default function ChordDiagram({ chordName, width = 120 }) {
  const parsed = parseChordName(chordName);
  if (!parsed) return null;
  
  const rootData = ukeDb.chords[parsed.root];
  if (!rootData) return null;

  let chordVariation = rootData.find(c => c.suffix === parsed.suffix);
  if (!chordVariation && parsed.suffix === 'major') {
     chordVariation = rootData.find(c => c.suffix === 'maj');
  }
  
  if (!chordVariation) return null;

  const position = chordVariation.positions[0];
  const frets = position.frets; // e.g. [0, 0, 0, 3]
  const baseFret = position.baseFret || 1;
  const numFrets = 4;
  const numStrings = 4;
  
  // Dimensions and styling
  const viewBoxSize = 100;
  const margin = 20;
  const gridWidth = viewBoxSize - margin * 2;
  const gridHeight = viewBoxSize - margin * 2.5; // leave room at bottom/top
  const stringSpacing = gridWidth / (numStrings - 1);
  const fretSpacing = gridHeight / numFrets;
  const radius = 5;

  return (
    <div className="chord-diagram" style={{ width: `${width}px` }}>
      <div className="chord-diagram-title">{chordName}</div>
      <svg viewBox="0 0 100 100" style={{ width: '100%', height: 'auto', display: 'block' }}>
        {/* Nut / Top Fret Line */}
        <line
          x1={margin}
          y1={margin}
          x2={margin + gridWidth}
          y2={margin}
          strokeWidth={baseFret === 1 ? 4 : 1}
          stroke="#d9c2ff"
        />

        {/* Frets (horizontal lines) */}
        {Array.from({ length: numFrets }).map((_, i) => (
          <line
            key={`fret-${i}`}
            x1={margin}
            y1={margin + (i + 1) * fretSpacing}
            x2={margin + gridWidth}
            y2={margin + (i + 1) * fretSpacing}
            strokeWidth={1}
            stroke="#d9c2ff"
          />
        ))}

        {/* Strings (vertical lines) */}
        {Array.from({ length: numStrings }).map((_, i) => (
          <line
            key={`string-${i}`}
            x1={margin + i * stringSpacing}
            y1={margin}
            x2={margin + i * stringSpacing}
            y2={margin + gridHeight}
            strokeWidth={1.5}
            stroke="#d9c2ff"
          />
        ))}

        {/* Base Fret Text (if > 1) */}
        {baseFret > 1 && (
          <text
            x={margin - 8}
            y={margin + fretSpacing / 2 + 4}
            fontSize="10"
            fill="#a89dac"
            textAnchor="end"
            fontFamily="monospace"
          >
            {baseFret}
          </text>
        )}

        {/* Fret Indicators (circles) and open/muted strings */}
        {frets.map((fret, stringIdx) => {
          const x = margin + stringIdx * stringSpacing;
          
          if (fret === -1) {
            // Muted string (X)
            return (
              <text key={`fret-mark-${stringIdx}`} x={x} y={margin - 6} fontSize="10" fill="#a89dac" textAnchor="middle" fontFamily="sans-serif">
                ×
              </text>
            );
          } else if (fret === 0) {
            // Open string (O)
            return (
              <text key={`fret-mark-${stringIdx}`} x={x} y={margin - 6} fontSize="9" fill="#a89dac" textAnchor="middle" fontFamily="sans-serif">
                ○
              </text>
            );
          } else {
            // Played fret (circle)
            const y = margin + (fret - 0.5) * fretSpacing;
            return (
              <circle
                key={`fret-mark-${stringIdx}`}
                cx={x}
                cy={y}
                r={radius}
                fill="#bea5eb"
              />
            );
          }
        })}
      </svg>
    </div>
  );
}
