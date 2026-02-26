/**
 * Renders an emoji using Twemoji (Twitter's open-source emoji set) for crisp,
 * consistent appearance across all platforms/OSes.
 *
 * CDN: https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/
 */

interface EmojiProps {
  /** The emoji character(s) to render */
  emoji: string;
  /** Rendered size in px (default 20) */
  size?: number;
  className?: string;
}

function getEmojiCodepoints(emoji: string): string {
  return [...emoji]
    .map((c) => c.codePointAt(0)!)
    .filter((cp) => cp !== 0xfe0f) // strip VS-16 variation selector
    .map((cp) => cp.toString(16))
    .join('-');
}

export function Emoji({ emoji, size = 20, className }: EmojiProps) {
  const codepoints = getEmojiCodepoints(emoji);
  const src = `https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/${codepoints}.svg`;

  return (
    <img
      src={src}
      alt={emoji}
      width={size}
      height={size}
      className={className}
      draggable={false}
      loading="lazy"
      style={{ display: 'inline-block', verticalAlign: 'middle', flexShrink: 0 }}
    />
  );
}
