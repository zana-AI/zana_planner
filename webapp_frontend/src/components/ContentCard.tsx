import { CheckCircle2, ExternalLink, FileText, Headphones, MoreHorizontal, Play, RotateCcw } from 'lucide-react';
import { HeatmapBar } from './HeatmapBar';
import type { UserContentWithDetails } from '../types';

interface ContentCardProps {
  item: UserContentWithDetails;
  onClick?: () => void;
  onStatusChange?: (status: 'saved' | 'in_progress' | 'completed') => void;
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

function getDisplayType(item: UserContentWithDetails): 'pdf' | 'video' | 'audio' | 'text' | 'other' {
  const provider = (item.provider || '').toLowerCase();
  const mime = String(item.metadata_json?.['mime_type'] || '').toLowerCase();
  if (provider === 'telegram_pdf' || mime === 'application/pdf') return 'pdf';
  return (item.content_type || 'other') as 'video' | 'audio' | 'text' | 'other';
}

function TypeIcon({ type }: { type: ReturnType<typeof getDisplayType> }) {
  if (type === 'video') return <Play size={17} />;
  if (type === 'audio') return <Headphones size={17} />;
  return <FileText size={17} />;
}

export function ContentCard({ item, onClick, onStatusChange }: ContentCardProps) {
  const title = item.title || 'Untitled';
  const provider = (item.provider || 'other').replace(/_/g, ' ');
  const displayType = getDisplayType(item);
  const durationSeconds = item.duration_seconds ?? item.estimated_read_seconds;
  const durationLabel = durationSeconds != null
    ? displayType === 'text' || displayType === 'pdf'
      ? `~${formatDuration(durationSeconds)} read`
      : formatDuration(durationSeconds)
    : '';
  const progressRatio = Math.max(0, Math.min(1, Number(item.progress_ratio || 0)));
  const markerRatio = item.position_unit === 'ratio' && typeof item.last_position === 'number'
    ? item.last_position
    : null;
  const buckets = item.buckets ?? [];
  const bucketCount = item.bucket_count ?? 120;
  const source = item.author_channel || provider;

  const secondaryStatus = item.status === 'completed'
    ? { label: 'Resume', icon: <RotateCcw size={15} />, value: 'in_progress' as const }
    : { label: 'Done', icon: <CheckCircle2 size={15} />, value: 'completed' as const };

  return (
    <article
      className="content-card"
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(event) => {
        if (!onClick) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      }}
    >
      <div className="content-card-media" aria-hidden="true">
        {item.thumbnail_url ? (
          <img src={item.thumbnail_url} alt="" />
        ) : (
          <div className="content-card-media-fallback">
            <TypeIcon type={displayType} />
          </div>
        )}
      </div>

      <div className="content-card-body">
        <div className="content-card-meta-row">
          <span className={`content-card-type content-card-type--${displayType}`}>
            <TypeIcon type={displayType} />
            {displayType}
          </span>
          <span className="content-card-status">{item.status.replace('_', ' ')}</span>
        </div>
        <h3 className="content-card-title">{title}</h3>
        <div className="content-card-subtitle">
          <span>{source}</span>
          {durationLabel && <span>{durationLabel}</span>}
          <span>{Math.round(progressRatio * 100)}% read</span>
        </div>
        <HeatmapBar
          data={{ bucket_count: bucketCount, buckets }}
          markerRatio={markerRatio}
          ariaLabel="Read coverage timeline"
          className="content-card-timeline"
        />
      </div>

      <div className="content-card-actions" onClick={(event) => event.stopPropagation()}>
        <button className="content-card-action" type="button" onClick={onClick} title="Open">
          <ExternalLink size={15} />
          <span>Open</span>
        </button>
        {onStatusChange && (
          <button
            className="content-card-action"
            type="button"
            onClick={() => onStatusChange(secondaryStatus.value)}
            title={secondaryStatus.label}
          >
            {secondaryStatus.icon}
            <span>{secondaryStatus.label}</span>
          </button>
        )}
        <button className="content-card-icon-action" type="button" title="More">
          <MoreHorizontal size={16} />
        </button>
      </div>
    </article>
  );
}
