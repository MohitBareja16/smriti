export function SmritiLogo({ size = 28 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 120 120"
      width={size}
      height={size}
      aria-label="Smriti"
      className="shrink-0"
    >
      <defs>
        <linearGradient id="smriti-logo-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1B2E40" />
          <stop offset="1" stopColor="#0E1A26" />
        </linearGradient>
      </defs>
      <rect width="120" height="120" rx="28" fill="url(#smriti-logo-bg)" />
      <path
        d="M60 60 A19 19 0 1 1 43.5 88.5"
        fill="none"
        stroke="#5B8FC7"
        strokeWidth="11"
        strokeLinecap="round"
      />
      <path
        d="M76.5 31.5 A19 19 0 1 0 60 60"
        fill="none"
        stroke="#E9A23B"
        strokeWidth="11"
        strokeLinecap="round"
      />
      <path
        d="M88 14 L90.6 21.4 L98 24 L90.6 26.6 L88 34 L85.4 26.6 L78 24 L85.4 21.4 Z"
        fill="#F6C56B"
      />
    </svg>
  );
}
