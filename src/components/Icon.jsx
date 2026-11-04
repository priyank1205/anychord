// A small, consistent icon set (24px grid, 1.75 stroke), drawn inline so it
// inherits colour and scales crisply.
const PATHS = {
  play: <path d="M8 5.5v13l10.5-6.5L8 5.5Z" fill="currentColor" stroke="none" />,
  pause: (
    <>
      <rect x="6.5" y="5" width="4" height="14" rx="1.2" fill="currentColor" stroke="none" />
      <rect x="13.5" y="5" width="4" height="14" rx="1.2" fill="currentColor" stroke="none" />
    </>
  ),
  prev: <path d="M17 6.5 9.5 12l7.5 5.5V6.5ZM7 6v12" />,
  next: <path d="M7 6.5 14.5 12 7 17.5V6.5ZM17 6v12" />,
  loop: <path d="M17 3.5 20 6.5l-3 3M20 6.5H8.5A4.5 4.5 0 0 0 4 11M7 20.5 4 17.5l3-3M4 17.5h11.5A4.5 4.5 0 0 0 20 13" />,
  edit: <path d="M14.5 5.5 18.5 9.5M4 20l1-4.5L15.8 4.7a1.8 1.8 0 0 1 2.5 0l1 1a1.8 1.8 0 0 1 0 2.5L8.5 19 4 20Z" />,
  copy: (
    <>
      <rect x="8.5" y="8.5" width="11" height="11" rx="2.2" />
      <path d="M15.5 8.5V6.2a1.7 1.7 0 0 0-1.7-1.7H6.2a1.7 1.7 0 0 0-1.7 1.7v7.6c0 .94.76 1.7 1.7 1.7h2.3" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  link: <path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1" />,
  external: <path d="M14 4.5h5.5V10M19.5 4.5 11 13M18 14v4a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 5 18V8a1.5 1.5 0 0 1 1.5-1.5h4" />,
  sound: <path d="M4.5 9.5v5h3.5l4.5 4v-13l-4.5 4H4.5ZM16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" />,
  alert: <path d="M12 8.5v4.5M12 16.5h.01M10.3 4.2 2.9 17.3A2 2 0 0 0 4.6 20.3h14.8a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z" />,
  info: <path d="M12 11v5.5M12 7.5h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />,
  sparkle: (
    <path d="M12 3.5 13.9 9 19.5 11 13.9 13 12 18.5 10.1 13 4.5 11 10.1 9 12 3.5ZM18.5 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7.7-1.8Z" />
  ),
  keyboard: (
    <>
      <rect x="3" y="6.5" width="18" height="11" rx="2" />
      <path d="M7 10h.01M10.3 10h.01M13.7 10h.01M17 10h.01M7.5 14h9" />
    </>
  ),
  minus: <path d="M6 12h12" />,
  reset: <path d="M4.5 12a7.5 7.5 0 1 0 2.4-5.5L4.5 8.8M4.5 4.2v4.6h4.6" />,
  chevron: <path d="m6 9 6 6 6-6" />,
  plus: <path d="M12 6v12M6 12h12" />,
  more: (
    <>
      <circle cx="6" cy="12" r="1.3" fill="currentColor" />
      <circle cx="12" cy="12" r="1.3" fill="currentColor" />
      <circle cx="18" cy="12" r="1.3" fill="currentColor" />
    </>
  ),
  wave: <path d="M3 12h2.5M7 8v8M10.5 5v14M14 9v6M17.5 7v10M21 12h0" />,
};

export default function Icon({ name, size = 20, className = "", title }) {
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      {PATHS[name]}
    </svg>
  );
}
