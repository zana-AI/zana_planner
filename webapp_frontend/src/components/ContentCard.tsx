/**
 * Content card: thumbnail, title, provider/type badges, duration/read-time, heatmap bar.
 */
import { HeatmapBar } from './HeatmapBar';
import type { UserContentWithDetails } from '../types';

interface ContentCardProps {
  item: UserContentWithDetails;
  onClick?: () => void;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const mm = m % 60;
    return mm ? `${h}h ${mm}m` : `${h}h`;
  }
  return s ? `${m}:${s.toString().padStart(2, '0')}` : `${m}m`;
}

export function ContentCard({ item, onClick }: ContentCardProps) {
  const title = item.title || 'Untitled';
  const provider = (item.provider || 'other').toLowerCase();
  const contentType = (item.content_type || 'other').toLowerCase();
  const durationSeconds = item.duration_seconds ?? item.estimated_read_seconds;
  const durationLabel = durationSeconds != null
    ? contentType === 'text'
      ? `~${formatDuration(durationSeconds)} read`
      : formatDuration(durationSeconds)
    : '';
  const thumbnailUrl = item.thumbnail_url;
  const buckets = item.buckets ?? [];
  const bucketCount = item.bucket_count ?? 120;

  return (
    <article
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      style={{
        background: 'rgba(255,255,255,0.06)',
        borderRadius: 12,
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,0.1)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'transform 0.2s, box-shadow 0.2s',
      }}
      onMouseEnter={(e) => {
        if (onClick) {
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.2)';
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = '';
        e.currentTarget.style.boxShadow = '';
      }}
    >
      <div style={{ aspectRatio: '16/9', position: 'relative', background: 'rgba(0,0,0,0.3)' }}>
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt=""
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
            }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'rgba(255,255,255,0.4)',
              fontSize: '2rem',
            }}
          >
            {contentType === 'video' ? '▶' : contentType === 'audio' ? '🎧' : '📄'}
          </div>
        )}
        <div
          style={{
            position: 'absolute',
            bottom: 6,
            left: 6,
            display: 'flex',
            gap: 4,
            flexWrap: 'wrap',
          }}
        >
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              textTransform: 'uppercase',
              background: 'rgba(0,0,0,0.7)',
              color: '#fff',
              padding: '2px 6px',
              borderRadius: 4,
            }}
          >
            {provider}
          </span>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              textTransform: 'uppercase',
              background: 'rgba(0,0,0,0.5)',
              color: 'rgba(255,255,255,0.9)',
              padding: '2px 6px',
              borderRadius: 4,
            }}
          >
            {contentType}
          </span>
          {durationLabel && (
            <span
              style={{
                fontSize: 10,
                background: 'rgba(0,0,0,0.6)',
                color: 'rgba(255,255,255,0.9)',
                padding: '2px 6px',
                borderRadius: 4,
              }}
            >
              {durationLabel}
            </span>
          )}
        </div>
      </div>
      <div style={{ padding: '10px 12px' }}>
        <h3
          style={{
            margin: 0,
            fontSize: 14,
            fontWeight: 600,
            color: '#fff',
            lineHeight: 1.3,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {title}
        </h3>
        <div style={{ marginTop: 8 }}>
          <HeatmapBar data={{ bucket_count: bucketCount, buckets }} />
        </div>
      </div>
    </article>
  );
}
