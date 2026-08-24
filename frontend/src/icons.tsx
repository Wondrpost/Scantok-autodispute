/** Inline SVG icons. Emoji were avoided deliberately: they render differently
 *  per platform and read as informal, which the dispute-verdict tone rules out. */

type Props = { className?: string };

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function IconCheck({ className = "icon" }: Props) {
  return (
    <svg {...base} className={className}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

export function IconCross({ className = "icon" }: Props) {
  return (
    <svg {...base} className={className}>
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

export function IconClock({ className = "icon" }: Props) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

export function IconWarning({ className = "icon" }: Props) {
  return (
    <svg {...base} className={className}>
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </svg>
  );
}

export function IconQuestion({ className = "icon" }: Props) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01" />
    </svg>
  );
}

export function IconBox({ className = "icon" }: Props) {
  return (
    <svg {...base} className={className}>
      <path d="m21 8-9-5-9 5v8l9 5 9-5V8Z" />
      <path d="m3 8 9 5 9-5M12 13v8" />
    </svg>
  );
}

export function IconCamera({ className = "icon" }: Props) {
  return (
    <svg {...base} className={className}>
      <rect x="1.5" y="5" width="14" height="14" rx="4" />
      <path d="M15.5 9.6l4-2.6c1.3-.85 3 .08 3 1.65v6.7c0 1.57-1.7 2.5-3 1.65l-4-2.6z" />
    </svg>
  );
}

export function IconGallery({ className = "icon" }: Props) {
  return (
    <svg {...base} className={className}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <path d="m21 15-5-5L5 21" />
    </svg>
  );
}

export function IconSignal({ className = "icon" }: Props) {
  return (
    <svg {...base} className={className}>
      <path d="M5 12.55a11 11 0 0 1 14 0M8.5 16.1a6 6 0 0 1 7 0M2 8.82a15 15 0 0 1 20 0M12 20h.01" />
    </svg>
  );
}
