/**
 * Thin horizontal heatmap bar: one slice per bucket, opacity = intensity (watch frequency).
 */
import type { HeatmapData } from '../types';

const BAR_HEIGHT = 6;
const DEFAULT_BUCKET_COUNT = 120;

interface HeatmapBarProps {
  data: HeatmapData | number[] | null | undefined;
  bucketCount?: number;
  className?: string;
  style?: React.CSSProperties;
}

export function HeatmapBar({ data, bucketCount = DEFAULT_BUCKET_COUNT, className, style }: HeatmapBarProps) {
  const buckets: number[] = Array.isArray(data)
    ? data
    : (data?.buckets ?? []);
  const count = data && typeof data === 'object' && 'bucket_count' in data
    ? (data as HeatmapData).bucket_count
    : bucketCount;
  const arr = buckets.length === count ? buckets : Array.from({ length: count }, (_, i) => buckets[i] ?? 0);
  const max = Math.max(1, ...arr);

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        width: '100%',
        height: BAR_HEIGHT,
        borderRadius: 2,
        overflow: 'hidden',
        backgroundColor: 'rgba(255,255,255,0.1)',
        ...style,
      }}
      role="img"
      aria-label="Watch progress heatmap"
    >
      {arr.map((value, i) => (
        <div
          key={i}
          style={{
            flex: 1,
            minWidth: 1,
            backgroundColor: 'var(--tg-theme-button-color, #2481cc)',
            opacity: value > 0 ? Math.min(1, 0.2 + (value / max) * 0.8) : 0,
            transition: 'opacity 0.15s ease',
          }}
        />
      ))}
    </div>
  );
}
