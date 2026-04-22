interface AppLogoProps {
  size?: number;
  title?: string;
}

export function AppLogo({ size = 28, title = 'Xaana' }: AppLogoProps) {
  return (
    <svg
      className="ui-app-logo"
      width={size}
      height={size}
      viewBox="0 0 559 531"
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <defs>
        <linearGradient id="xaana-logo-gradient" x1="0" y1="0" x2="559" y2="531" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#9ff8f4" />
          <stop offset="0.52" stopColor="#c7dbff" />
          <stop offset="1" stopColor="#f36dff" />
        </linearGradient>
      </defs>
      <ellipse
        cx="279.5"
        cy="265.5"
        rx="253"
        ry="239"
        fill="none"
        stroke="url(#xaana-logo-gradient)"
        strokeWidth="18"
      />
      <path
        d="M122 168 C190 172 234 199 276 251"
        fill="none"
        stroke="url(#xaana-logo-gradient)"
        strokeWidth="18"
        strokeLinecap="round"
      />
      <path
        d="M437 168 C352 173 321 224 273 282 C231 332 189 351 122 360"
        fill="none"
        stroke="url(#xaana-logo-gradient)"
        strokeWidth="18"
        strokeLinecap="round"
      />
      <path
        d="M300 267 C338 321 377 352 437 360"
        fill="none"
        stroke="url(#xaana-logo-gradient)"
        strokeWidth="18"
        strokeLinecap="round"
      />
    </svg>
  );
}
