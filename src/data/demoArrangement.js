export const DEMO_ARRANGEMENT = {
  title: "First Light",
  artist: "AnyChords Studio",
  key: "C major",
  tempo: 92,
  meter: "4/4",
  source: "AnyChords preview arrangement",
  confidence: "Preview",
  sections: [
    { name: "Intro", label: "4 bars", rows: [["C", "G/B", "Am7", "Fmaj7"]] },
    {
      name: "Verse 1",
      label: "8 bars",
      rows: [
        ["C", "G", "Am7", "F"],
        ["C", "G", "F", "F"],
      ],
    },
    {
      name: "Chorus",
      label: "8 bars",
      rows: [
        ["F", "G", "Em7", "Am7"],
        ["F", "G", "C", "C"],
      ],
    },
    { name: "Bridge", label: "4 bars", rows: [["Am7", "G", "Fmaj7", "Gsus4  G"]] },
  ],
};
