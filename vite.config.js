import { defineConfig } from "vite";

// AnyChords' own ports sit away from the ones dev tools grab first (Vite's
// 5173, Python backends' 8000), so it rarely clashes with other apps on this
// computer. If they are busy anyway, `npm start` picks the next free ones and
// tells this server where the analyser is through ANYCHORDS_API_PORT.
const analyser = `http://127.0.0.1:${process.env.ANYCHORDS_API_PORT || 8288}`;

// The page reaches the analyser through this server, at its own address, so it
// works on whatever port it gets, and other sites can't call the analyser.
const proxy = { "/api": { target: analyser, changeOrigin: true } };

export default defineConfig({
  server: { port: 5288, proxy },
  preview: { proxy },
});
