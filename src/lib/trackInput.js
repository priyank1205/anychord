export function spotifyTrackId(value) {
  const trimmed = value.trim();
  const urlMatch = trimmed.match(/(?:open|play)\.spotify\.com\/(?:intl-[a-z-]+\/)?track\/([A-Za-z0-9]{22})(?:[/?#]|$)/i);
  const uriMatch = trimmed.match(/^spotify:track:([A-Za-z0-9]{22})$/i);
  return urlMatch?.[1] ?? uriMatch?.[1] ?? null;
}

export function spotifyTrackUrl(trackId) {
  return `https://open.spotify.com/track/${trackId}`;
}

export function youtubeVideoId(value) {
  const trimmed = value.trim();
  try {
    const url = new URL(trimmed);
    const host = url.hostname.replace(/^www\./, "").toLowerCase();
    if (host === "youtu.be") return url.pathname.split("/").filter(Boolean)[0] ?? null;
    if (host === "youtube.com" || host === "m.youtube.com") {
      if (url.pathname === "/watch") return url.searchParams.get("v");
      const parts = url.pathname.split("/").filter(Boolean);
      if (["embed", "shorts", "live"].includes(parts[0])) return parts[1] ?? null;
    }
  } catch {
    return null;
  }
  return null;
}

export function youtubeEmbedUrl(videoId) {
  return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(videoId)}?rel=0`;
}
