/* global React */
// Inline-SVG icon set, modeled on lucide. Stroke-based, currentColor.
// Add icons here as the prototype needs them.

const ICON_DEFS = {
  "calendar-check": (
    <>
      <path d="M21 8H3"/>
      <rect x="3" y="4" width="18" height="18" rx="2"/>
      <path d="M16 2v4M8 2v4"/>
      <path d="m9 16 2 2 4-4"/>
    </>
  ),
  users: (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </>
  ),
  compass: (
    <>
      <circle cx="12" cy="12" r="10"/>
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="10"/>
      <circle cx="12" cy="12" r="6"/>
      <circle cx="12" cy="12" r="2"/>
    </>
  ),
  plus: (
    <>
      <path d="M12 5v14M5 12h14"/>
    </>
  ),
  "chevron-left": <path d="m15 18-6-6 6-6"/>,
  "chevron-right": <path d="m9 18 6-6-6-6"/>,
  "arrow-left": (
    <>
      <path d="m12 19-7-7 7-7"/>
      <path d="M19 12H5"/>
    </>
  ),
  x: (
    <>
      <path d="M18 6 6 18"/>
      <path d="m6 6 12 12"/>
    </>
  ),
  play: <polygon points="6 3 20 12 6 21 6 3" fill="currentColor" stroke="none"/>,
  pause: (
    <>
      <rect x="6" y="4" width="4" height="16" fill="currentColor" stroke="none"/>
      <rect x="14" y="4" width="4" height="16" fill="currentColor" stroke="none"/>
    </>
  ),
  timer: (
    <>
      <line x1="10" y1="2" x2="14" y2="2"/>
      <line x1="12" y1="14" x2="15" y2="11"/>
      <circle cx="12" cy="14" r="8"/>
    </>
  ),
  bell: (
    <>
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>
    </>
  ),
  brain: (
    <>
      <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>
      <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>
    </>
  ),
  send: (
    <>
      <path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/>
      <path d="m21.854 2.147-10.94 10.939"/>
    </>
  ),
  "trending-down": (
    <>
      <polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/>
      <polyline points="16 17 22 17 22 11"/>
    </>
  ),
  mic: (
    <>
      <rect x="9" y="2" width="6" height="13" rx="3"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" y1="19" x2="12" y2="22"/>
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="10"/>
      <line x1="2" y1="12" x2="22" y2="12"/>
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
    </>
  ),
  flame: <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>,
  check: <path d="M20 6 9 17l-5-5"/>,
  trash: (
    <>
      <path d="M3 6h18"/>
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </>
  ),
  "more-horizontal": (
    <>
      <circle cx="12" cy="12" r="1"/>
      <circle cx="19" cy="12" r="1"/>
      <circle cx="5" cy="12" r="1"/>
    </>
  ),
  settings: (
    <>
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
      <circle cx="12" cy="12" r="3"/>
    </>
  ),
  "user-plus": (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <line x1="19" y1="8" x2="19" y2="14"/>
      <line x1="22" y1="11" x2="16" y2="11"/>
    </>
  ),
  book: (
    <>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
    </>
  ),
  dumbbell: (
    <>
      <path d="m6.5 6.5 11 11"/>
      <path d="m21 21-1-1"/>
      <path d="m3 3 1 1"/>
      <path d="m18 22 4-4"/>
      <path d="m2 6 4-4"/>
      <path d="m3 10 7-7"/>
      <path d="m14 21 7-7"/>
    </>
  ),
  pencil: (
    <>
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
      <path d="M18.375 2.625a1 1 0 0 1 3 3l-9.013 9.014a2 2 0 0 1-.853.505l-2.873.84a.5.5 0 0 1-.62-.62l.84-2.873a2 2 0 0 1 .506-.852z"/>
    </>
  ),
  shield: <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>,
  "users-round": (
    <>
      <path d="M18 21a8 8 0 0 0-16 0"/>
      <circle cx="10" cy="8" r="5"/>
      <path d="M22 20c0-3.37-2-6.5-4-8a5 5 0 0 0-.45-8.3"/>
    </>
  ),
  "book-open": (
    <>
      <path d="M12 7v14"/>
      <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>
    </>
  ),
  library: (
    <>
      <path d="m16 6 4 14"/>
      <path d="M12 6v14"/>
      <path d="M8 8v12"/>
      <path d="M4 4v16"/>
    </>
  ),
  calendar: (
    <>
      <path d="M8 2v4M16 2v4"/>
      <rect x="3" y="4" width="18" height="18" rx="2"/>
      <path d="M3 10h18"/>
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="10"/>
      <polyline points="12 6 12 12 16 14"/>
    </>
  ),
  "file-text": (
    <>
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>
      <path d="M14 2v4a2 2 0 0 0 2 2h4"/>
      <path d="M10 9H8M16 13H8M16 17H8"/>
    </>
  ),
  video: (
    <>
      <path d="m22 8-6 4 6 4V8Z"/>
      <rect x="2" y="6" width="14" height="12" rx="2"/>
    </>
  ),
  headphones: (
    <>
      <path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H4a1 1 0 0 1-1-1z"/>
      <path d="M21 14h-3a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h2a1 1 0 0 0 1-1z"/>
      <path d="M3 14a9 9 0 0 1 18 0"/>
    </>
  ),
  "chevron-down": <path d="m6 9 6 6 6-6"/>,
  "chevron-up":   <path d="m18 15-6-6-6 6"/>,
  link: (
    <>
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
    </>
  ),
  bookmark: <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>,
  bot: (
    <>
      <path d="M12 8V4H8"/>
      <rect x="2" y="8" width="20" height="12" rx="2"/>
      <path d="M2 14h2M20 14h2M15 13v2M9 13v2"/>
    </>
  ),
};

function Icon({ name, size = 18, strokeWidth = 1.75, color, style }) {
  const body = ICON_DEFS[name];
  if (!body) return null;
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke={color || "currentColor"}
      strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"
      style={{ display: "inline-block", flexShrink: 0, ...style }}
      aria-hidden="true">
      {body}
    </svg>
  );
}

window.Icon = Icon;
