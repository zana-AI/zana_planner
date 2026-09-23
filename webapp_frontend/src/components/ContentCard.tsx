import { useTranslation } from 'react-i18next';
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { CalendarClock, Captions, FileText, Headphones, Play, Share2, Trash2 } from 'lucide-react';
import { apiClient } from '../api/client';
import { HeatmapBar } from './HeatmapBar';
import { RemoveContentConfirmModal } from './RemoveContentConfirmModal';
import type { UserContentWithDetails } from '../types';

interface ContentCardProps {
  item: UserContentWithDetails;
  onClick?: () => void;
  /** Open the "when will you do this?" sheet for this item. */
  onPlan?: () => void;
  /** Hand out a public link. Only set for items that actually have one. */
  onShare?: () => void;
  /** Swipe-to-delete, confirmed. Archives the item — it can't be restored
   *  from the UI yet, so this always asks first. */
  onArchive?: () => void;
}

/** Pixels the card slides to reveal the delete action. Matches the button's
 * own width plus its side padding, so the reveal stops exactly at its edge. */
const REVEAL_WIDTH = 72;
// A move shorter than this is a tap, not a swipe — keeps a slightly shaky
// finger from accidentally starting a drag.
const SWIPE_START_THRESHOLD = 8;

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

export function ContentCard({ item, onClick, onPlan, onShare, onArchive }: ContentCardProps) {
  const { t } = useTranslation();
  const [generatedThumbnailUrl, setGeneratedThumbnailUrl] = useState('');
  const [confirmingRemove, setConfirmingRemove] = useState(false);
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

  // --- swipe-to-reveal-delete --------------------------------------------
  // A card slides away from its inline-end edge to reveal one fixed
  // delete button behind it — the same gesture as a mail app's swipe. It
  // only ever *reveals* the button; deleting still needs a tap and a
  // confirmation, since this can't be undone from the UI yet.
  const [dragX, setDragX] = useState(0);
  const [dragging, setDragging] = useState(false);
  const revealedRef = useRef(false);
  // The authoritative position lives here, not in `dragX` state: several
  // pointermove events can fire before React commits the re-render they
  // triggered, so a release handler reading `dragX` from its own closure can
  // see a stale (often still-zero) value. `dragX` state exists only to
  // trigger the re-render that paints the transform.
  const dragXRef = useRef(0);
  // `sign` is the direction the card slides to uncover the button, which
  // sits on the inline-end edge: the right in LTR, so the card slides left
  // (-1); the left in RTL, so it slides right (+1).
  const dragRef = useRef<{ startX: number; startY: number; originX: number; axis: 'x' | 'y' | null; pointerId: number; sign: 1 | -1 } | null>(null);

  const snapTo = (x: number) => {
    revealedRef.current = x !== 0;
    dragXRef.current = x;
    setDragX(x);
  };

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    // Pointer Events cover touch and mouse the same way, so a click-drag
    // reveals the delete button on a trackpad exactly as a swipe does on a
    // phone — there's no separate button for non-touch to keep in sync.
    if (!onArchive) return;
    const sign = getComputedStyle(event.currentTarget).direction === 'rtl' ? 1 : -1;
    dragRef.current = { startX: event.clientX, startY: event.clientY, originX: dragXRef.current, axis: null, pointerId: event.pointerId, sign };
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (drag.axis === null) {
      if (Math.abs(dx) < SWIPE_START_THRESHOLD && Math.abs(dy) < SWIPE_START_THRESHOLD) return;
      drag.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
      if (drag.axis === 'x') {
        event.currentTarget.setPointerCapture(event.pointerId);
        setDragging(true);
      }
    }
    if (drag.axis !== 'x') return;
    event.preventDefault();
    // Distance slid toward the button's side, clamped to [0, a little past it].
    const progress = Math.min(REVEAL_WIDTH + 24, Math.max(0, drag.sign * (drag.originX + dx)));
    const next = drag.sign * progress;
    dragXRef.current = next;
    setDragX(next);
  };

  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    dragRef.current = null;
    setDragging(false);
    if (!drag || drag.axis !== 'x') return;
    snapTo(Math.abs(dragXRef.current) > REVEAL_WIDTH / 2 ? drag.sign * REVEAL_WIDTH : 0);
  };

  const handleCardClick = () => {
    if (revealedRef.current) {
      snapTo(0);
      return;
    }
    onClick?.();
  };

  return (
    <>
      <div className="content-card-swipe">
        {/* Mounted only while dragging/revealed: the card's own background is
            translucent by design, so a button sitting behind it at rest would
            tint the card's edge with red even when nothing is happening. */}
        {onArchive && dragX !== 0 && (
          <button
            type="button"
            className="content-card-swipe-delete"
            style={{ width: REVEAL_WIDTH }}
            onClick={() => { snapTo(0); setConfirmingRemove(true); }}
            aria-label={t('content.removeFromLibrary')}
          >
            <Trash2 size={18} />
          </button>
        )}
        <article
          className="content-card"
          onClick={handleCardClick}
          role={onClick ? 'button' : undefined}
          tabIndex={onClick ? 0 : undefined}
          onKeyDown={(event) => {
            if (!onClick || event.target !== event.currentTarget) return;
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              onClick();
            }
          }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          style={{ transform: dragX ? `translateX(${dragX}px)` : undefined, transition: dragging ? 'none' : undefined }}
        >
          <div className="content-card-media-col">
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
            {/* The two actions worth a permanent slot: everything else is a
                tap on the card (open), a swipe (delete), or not needed. */}
            {(onPlan || onShare) && (
              <div className="content-card-quick-actions" onClick={(event) => event.stopPropagation()}>
                {onPlan && (
                  <button type="button" onClick={onPlan} aria-label={t('content.planIt')} title={t('content.planIt')}>
                    <CalendarClock size={15} />
                  </button>
                )}
                {onShare && (
                  <button type="button" onClick={onShare} aria-label={t('content.share')} title={t('content.share')}>
                    <Share2 size={15} />
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="content-card-body">
            <div className="content-card-meta-row">
              <div className="content-card-meta-tags">
                <span className={`content-card-type content-card-type--${displayType}`}>
                  <TypeIcon type={displayType} />
                  {t(`content.types.${displayType}`)}
                </span>
                {item.has_subtitles && displayType === 'video' ? (
                  <span className="content-card-subtitles" title={t('content.subtitlesAvailable')}>
                    <Captions size={14} aria-hidden="true" />
                    {t('content.subtitlesAvailable')}
                  </span>
                ) : null}
              </div>
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
        </article>
      </div>

      <RemoveContentConfirmModal
        isOpen={confirmingRemove}
        title={title}
        onCancel={() => setConfirmingRemove(false)}
        onConfirm={() => { setConfirmingRemove(false); onArchive?.(); }}
      />
    </>
  );
}
