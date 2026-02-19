interface AppLogoProps {
  size?: number;
  title?: string;
}

export function AppLogo({ size = 28, title = 'Xaana' }: AppLogoProps) {
  return (
    <img
      className="ui-app-logo"
      src="/assets/xaana_icon_dark.png"
      width={size}
      height={size}
      alt={title}
      title={title}
    />
  );
}
