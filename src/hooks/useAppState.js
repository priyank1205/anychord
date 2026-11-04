import { useEffect, useState } from "react";

// State that survives reloads (per browser). Storage can be unavailable in
// private windows, so every access is guarded.
export function useStoredState(key, initial, allowed) {
  const [value, setValue] = useState(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored !== null && (!allowed || allowed.includes(stored)) ? stored : initial;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Not persisted; the setting still works for this visit.
    }
  }, [key, value]);
  return [value, setValue];
}

export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);
  return matches;
}
