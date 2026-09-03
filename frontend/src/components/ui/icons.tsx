import type { SVGProps } from "react";

type Props = SVGProps<SVGSVGElement> & { size?: number };

function make(path: React.ReactNode, name: string) {
  const Icon = ({ size = 18, ...rest }: Props) => (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...rest}
    >
      {path}
    </svg>
  );
  Icon.displayName = name;
  return Icon;
}

/* A small, consistent stroke set (Lucide-style, 1.75px). Add here, never inline SVG in features. */
export const Icons = {
  user: make(<><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>, "User"),
  stethoscope: make(<><path d="M5 3v6a5 5 0 0 0 10 0V3" /><path d="M10 14v2a5 5 0 0 0 10 0v-1" /><circle cx="20" cy="12" r="2" /></>, "Stethoscope"),
  building: make(<><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 21V13h6v8M7 7h2M11 7h2M15 7h2M7 11h2M15 11h2" /></>, "Building"),
  settings: make(<><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>, "Settings"),
  send: make(<><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4z" /></>, "Send"),
  paperclip: make(<path d="m21.4 11.05-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5" />, "Paperclip"),
  check: make(<path d="M20 6 9 17l-5-5" />, "Check"),
  checkCircle: make(<><circle cx="12" cy="12" r="9" /><path d="m8.5 12 2.5 2.5 4.5-5" /></>, "CheckCircle"),
  x: make(<path d="M18 6 6 18M6 6l12 12" />, "X"),
  alert: make(<><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></>, "Alert"),
  info: make(<><circle cx="12" cy="12" r="9" /><path d="M12 16v-4M12 8h.01" /></>, "Info"),
  clock: make(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>, "Clock"),
  calendar: make(<><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>, "Calendar"),
  file: make(<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>, "File"),
  image: make(<><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.5" /><path d="m21 16-5-5-9 9" /></>, "Image"),
  search: make(<><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>, "Search"),
  chevronRight: make(<path d="m9 6 6 6-6 6" />, "ChevronRight"),
  chevronLeft: make(<path d="m15 6-6 6 6 6" />, "ChevronLeft"),
  chevronDown: make(<path d="m6 9 6 6 6-6" />, "ChevronDown"),
  arrowLeft: make(<><path d="M19 12H5" /><path d="m12 19-7-7 7-7" /></>, "ArrowLeft"),
  arrowRight: make(<><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></>, "ArrowRight"),
  plus: make(<path d="M12 5v14M5 12h14" />, "Plus"),
  trash: make(<><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /></>, "Trash"),
  edit: make(<><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></>, "Edit"),
  shield: make(<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />, "Shield"),
  sparkles: make(<><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /><circle cx="12" cy="12" r="3" /></>, "Sparkles"),
  bot: make(<><rect x="4" y="8" width="16" height="12" rx="3" /><path d="M12 4v4M8 13h.01M16 13h.01M9 17h6" /></>, "Bot"),
  activity: make(<path d="M3 12h4l3-8 4 16 3-8h4" />, "Activity"),
  list: make(<><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3 6h.01M3 12h.01M3 18h.01" /></>, "List"),
  grid: make(<><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>, "Grid"),
  link: make(<><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></>, "Link"),
  sun: make(<><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>, "Sun"),
  moon: make(<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />, "Moon"),
  refresh: make(<><path d="M21 12a9 9 0 1 1-2.6-6.4" /><path d="M21 3v6h-6" /></>, "Refresh"),
  upload: make(<><path d="M12 16V4" /><path d="m6 10 6-6 6 6" /><path d="M4 20h16" /></>, "Upload"),
  download: make(<><path d="M12 4v12" /><path d="m6 10 6 6 6-6" /><path d="M4 20h16" /></>, "Download"),
  pill: make(<><rect x="3" y="9" width="18" height="6" rx="3" transform="rotate(-45 12 12)" /><path d="m8.5 8.5 7 7" /></>, "Pill"),
  heart: make(<path d="M19.5 12.6 12 20l-7.5-7.4a4.6 4.6 0 0 1 6.5-6.5l1 1 1-1a4.6 4.6 0 0 1 6.5 6.5z" />, "Heart"),
  mic: make(<><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>, "Mic"),
  video: make(<><rect x="3" y="6" width="13" height="12" rx="2" /><path d="m16 10 5-3v10l-5-3" /></>, "Video"),
  mapPin: make(<><path d="M12 22s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z" /><circle cx="12" cy="10" r="2.5" /></>, "MapPin"),
  menu: make(<path d="M4 7h16M4 12h16M4 17h16" />, "Menu"),
  external: make(<><path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5" /></>, "External"),
  database: make(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>, "Database"),
  flag: make(<><path d="M4 22V4" /><path d="M4 4h12l-2 4 2 4H4" /></>, "Flag"),
};

export type IconName = keyof typeof Icons;