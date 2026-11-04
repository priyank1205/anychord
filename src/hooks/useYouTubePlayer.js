import { useCallback, useEffect, useRef, useState } from "react";

let apiPromise = null;

function loadYouTubeApi() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (!apiPromise) {
    apiPromise = new Promise((resolve) => {
      const previous = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        previous?.();
        resolve(window.YT);
      };
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.async = true;
      document.head.appendChild(script);
    });
  }
  return apiPromise;
}

// Wraps the YouTube IFrame player. `onFrame(time)` is called every animation
// frame while playing (and once after a seek), without re-rendering React.
export function useYouTubePlayer(videoId, onFrame) {
  const hostRef = useRef(null);
  const playerRef = useRef(null);
  const frameRef = useRef(onFrame);
  const rafRef = useRef(0);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [rate, setRateState] = useState(1);
  const [duration, setDuration] = useState(0);
  const [title, setTitle] = useState("");

  frameRef.current = onFrame;

  const currentTime = useCallback(() => {
    const player = playerRef.current;
    return player && typeof player.getCurrentTime === "function" ? player.getCurrentTime() : 0;
  }, []);

  useEffect(() => {
    if (!videoId || !hostRef.current) return undefined;
    let cancelled = false;
    setReady(false);
    setPlaying(false);
    setTitle("");

    loadYouTubeApi().then((YT) => {
      if (cancelled || !hostRef.current) return;
      const mount = document.createElement("div");
      hostRef.current.replaceChildren(mount);
      playerRef.current = new YT.Player(mount, {
        videoId,
        width: "100%",
        height: "100%",
        playerVars: { playsinline: 1, rel: 0, modestbranding: 1, origin: window.location.origin },
        events: {
          onReady: (event) => {
            if (cancelled) return;
            setReady(true);
            setDuration(event.target.getDuration?.() || 0);
            setTitle(event.target.getVideoData?.()?.title || "");
          },
          onStateChange: (event) => {
            const isPlaying = event.data === YT.PlayerState.PLAYING;
            setPlaying(isPlaying);
            if (isPlaying) setDuration(event.target.getDuration?.() || 0);
            frameRef.current?.(event.target.getCurrentTime?.() || 0);
          },
          onPlaybackRateChange: (event) => setRateState(event.data),
        },
      });
    });

    return () => {
      cancelled = true;
      try {
        playerRef.current?.destroy?.();
      } catch {
        // The iframe may already be gone.
      }
      playerRef.current = null;
    };
  }, [videoId]);

  useEffect(() => {
    if (!playing) return undefined;
    const tick = () => {
      frameRef.current?.(currentTime());
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [playing, currentTime]);

  const play = useCallback(() => playerRef.current?.playVideo?.(), []);
  const pause = useCallback(() => playerRef.current?.pauseVideo?.(), []);
  const toggle = useCallback(() => (playing ? pause() : play()), [playing, play, pause]);
  const seek = useCallback((time) => {
    const player = playerRef.current;
    if (!player?.seekTo) return;
    player.seekTo(Math.max(0, time), true);
    frameRef.current?.(Math.max(0, time));
  }, []);
  const setRate = useCallback((value) => {
    playerRef.current?.setPlaybackRate?.(value);
    setRateState(value);
  }, []);

  return { hostRef, ready, playing, rate, duration, title, currentTime, play, pause, toggle, seek, setRate };
}
