import Icon from "./Icon";

export const SIGN_IN_BROWSERS = [
  ["chrome", "Chrome"],
  ["safari", "Safari"],
  ["firefox", "Firefox"],
  ["brave", "Brave"],
  ["edge", "Edge"],
];

const TITLES = {
  bot_check: "YouTube wants to check you’re not a bot",
  rate_limited: "YouTube is slowing down downloads",
  age_restricted: "This video needs a YouTube sign-in",
  cookies_permission: "macOS blocked access to Safari",
  cookies_missing: "That browser isn’t on this computer",
  cookies_locked: "Your Mac didn’t share the sign-in",
  private: "This video is private",
  members_only: "This video is for channel members",
  unavailable: "This video isn’t available",
  live: "Live streams can’t be charted yet",
  network: "Can’t reach YouTube",
  outdated: "The YouTube downloader needs an update",
  timeout: "The download took too long",
  not_installed: "Something is missing",
  conversion_failed: "The audio couldn’t be read",
  offline: "AnyChords isn’t running",
  bad_link: "That’s not a YouTube link",
};

// Problems a browser's YouTube sign-in can fix, and ones worth simply retrying.
const SIGN_IN = new Set(["bot_check", "rate_limited", "age_restricted", "cookies_permission", "cookies_missing", "cookies_locked"]);
const RETRY = new Set([
  "bot_check",
  "rate_limited",
  "network",
  "timeout",
  "outdated",
  "offline",
  "download_failed",
  "failed",
  "cookies_locked",
]);

// What went wrong, in plain words, with the one thing to do about it.
export default function ProblemCard({ problem, browser, busy, onUseBrowser, onRetry }) {
  const signIn = SIGN_IN.has(problem.code);
  return (
    <div className={`problem ${signIn ? "problem--sign-in" : ""}`} role="alert">
      <Icon name={signIn ? "info" : "alert"} size={20} className="problem__icon" />
      <div className="problem__body">
        <h2>{TITLES[problem.code] ?? "The chart couldn’t be made"}</h2>
        <p>{problem.message}</p>

        {signIn && (
          <div className="problem__sign-in">
            <p className="problem__ask">Which browser are you signed in to YouTube with?</p>
            <div className="problem__browsers">
              {SIGN_IN_BROWSERS.map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`chip ${browser === value ? "chip--accent" : ""}`}
                  onClick={() => onUseBrowser(value)}
                  disabled={busy}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="problem__note">
              Your Mac may ask for your password: choose <strong>Always Allow</strong> (Firefox doesn’t ask). The sign-in stays on this
              computer and is only used when YouTube blocks a download.
            </p>
            <p className="problem__note">
              Heads-up: yt-dlp, the downloader inside AnyChords, warns that heavy downloading can get an account flagged. AnyChords fetches
              one song at a time and keeps the ones you’ve charted.
            </p>
          </div>
        )}

        {RETRY.has(problem.code) && (
          <button type="button" className="ghost-btn problem__retry" onClick={onRetry} disabled={busy}>
            <Icon name="reset" size={15} /> Try again
          </button>
        )}

        {problem.details && (
          <details className="problem__details">
            <summary>Technical details</summary>
            <pre>{problem.details}</pre>
          </details>
        )}
      </div>
    </div>
  );
}
