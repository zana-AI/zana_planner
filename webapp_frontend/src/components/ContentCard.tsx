import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { CalendarClock, CheckCircle2, ExternalLink, FileText, Headphones, Play, RotateCcw, Share2 } from 'lucide-react';
import { apiClient } from '../api/client';
import { HeatmapBar } from './HeatmapBar';
import type { UserContentWithDetails } from '../types';

interface ContentCardProps {
  item: UserContentWithDetails;
  onClick?: () => void;
  onStatusChange?: (status: 'saved' | 'in_progress' | 'completed') => void;
  /** Open the "when will you do this?" sheet for this item. */
  onPlan?: () => void;
  /** Hand out a public link. Only set for items that actually have one. */
  onShare?: () => void;
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

export function ContentCard({ item, onClick, onStatusChange, onPlan, onShare }: ContentCardProps) {
  const { t } = useTranslation();
  const [generatedThumbnailUrl, setGeneratedThumbnailUrl] = useState('');
  const title = item.title || t('content.untitled');
  const provider = (item.provider || 'other').replace(/_/g, ' ');
  const displayType = getDisplayType(item);
  const durationSeconds = item.duration_seconds ?? item.estimated_read_seconds;
  const durationLabel = durationSeconds != null
    ? displayType === 'text' || displayType === 'pdf'
      ? t('content.readDuration', { duration: `~${formatDuration(durationSeconds)}` })
      : formatDuration(durationSeconds)
    : '';
  const progressRatio = Math.max(0, Math.min(1, Number(item.progress_ratio || 0)));
  const markerRatio = item.position_unit === 'ratio' && typeof item.last_position === 'number'
    ? item.last_position
    : null;
  const buckets = item.buckets ?? [];
  const bucketCount = item.bucket_count ?? 120;
  const source = item.author_channel || (provider === 'youtube' ? 'YouTube' : provider);
  const thumbnailUrl = item.thumbnail_url || generatedThumbnailUrl;
  const pdfCoverTitle = title
    .replace(/\.pdf$/i, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const pageCount = Number(item.metadata_json?.['page_count'] || 0);

  useEffect(() => {
    if (item.thumbnail_url || !item.thumbnail_asset_id || displayType !== 'pdf') {
      setGeneratedThumbnailUrl('');
      return undefined;
    }
    let active = true;
    let objectUrl = '';
    void apiClient.fetchContentThumbnailBlob(item.content_id || item.id)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setGeneratedThumbnailUrl(objectUrl);
      })
      .catch(() => {
        if (active) setGeneratedThumbnailUrl('');
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [displayType, item.content_id, item.id, item.thumbnail_asset_id, item.thumbnail_url]);

  const secondaryStatus = item.status === 'completed'
      ? { label: t('content.resume'), icon: <RotateCcw size={15} />, value: 'in_progress' as const }
    : { label: t('content.markComplete'), icon: <CheckCircle2 size={15} />, value: 'completed' as const };

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
        {thumbnailUrl ? (
          <img src={thumbnailUrl} alt="" className={displayType === 'pdf' ? 'content-card-pdf-thumbnail' : undefined} />
        ) : displayType === 'pdf' ? (
          <div className="content-card-pdf-cover">
            <FileText size={18} />
            <strong>{pdfCoverTitle || t('content.types.pdf')}</strong>
            {pageCount > 0 ? <small>{t('content.pages', { count: pageCount })}</small> : null}
          </div>
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
            {t(`content.types.${displayType}`)}
          </span>
          <span className="content-card-status">{t(`content.status.${item.status}`, item.status.replace('_', ' '))}</span>
        </div>
        <h3 className="content-card-title">{title}</h3>
        <div className="content-card-subtitle">
          <span>{source}</span>
          {durationLabel && <span>{durationLabel}</span>}
          <span>{t('content.progressRead', { percent: Math.round(progressRatio * 100) })}</span>
        </div>
        <HeatmapBar
          data={{ bucket_count: bucketCount, buckets }}
          markerRatio={markerRatio}
          ariaLabel={t('content.readCoverageTimeline')}
          className="content-card-timeline"
        />
      </div>

      <div className="content-card-actions" onClick={(event) => event.stopPropagation()}>
        <button className="content-card-action" type="button" onClick={onClick} title={t('content.open')}>
          <ExternalLink size={15} />
          <span>{t('content.open')}</span>
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
        {onPlan && (
          <button
            className="content-card-action"
            type="button"
            onClick={onPlan}
            title={t('content.planIt')}
          >
            <CalendarClock size={15} />
            <span>{t('content.planIt')}</span>
          </button>
        )}
        {onShare && (
          <button
            className="content-card-action"
            type="button"
            onClick={onShare}
            title={t('content.share')}
          >
            <Share2 size={15} />
            <span>{t('content.share')}</span>
          </button>
        )}
      </div>
    </article>
  );
}
