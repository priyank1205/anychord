import { useCallback, useEffect, useState } from "react";

// State that survives reloads (per browser). Only a value the person picks is
// saved, so a later change of default still reaches people who never chose.
// Storage can be unavailable in private windows, so every access is guarded.
export function useStoredState(key, initial, allowed) {
  const [value, setValue] = useState(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored !== null && (!allowed || allowed.includes(stored)) ? stored : initial;
    } catch {
      return initial;
    }
  });
  const choose = useCallback(
    (next) =>
      setValue((current) => {
        const resolved = typeof next === "function" ? next(current) : next;
        try {
          window.localStorage.setItem(key, resolved);
        } catch {
          // Not persisted; the setting still works for this visit.
        }
        return resolved;
      }),
    [key],
  );
  return [value, choose];
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
