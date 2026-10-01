import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Bookmark, BookOpen, FileText, GraduationCap, Layers, Play, Repeat, Video } from 'lucide-react';
import { apiClient } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { itemKind } from '../pages/exploreVocabulary';
import { youTubeUrlFor, videoDuration, type LearningEntry } from '../utils/exploreLearning';
import { saveActionKey } from '../utils/learningActions';
import { YouTubeThumbnailMark } from './YouTubeThumbnailMark';
import { ContentMetadataBadges } from './ContentMetadataBadges';

const icons = { video: Video, course: GraduationCap, deck: Layers, book: BookOpen, habit: Repeat };

export function ExploreCard({ entry, onSaved }: { entry: LearningEntry; onSaved?: () => void }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [state, setState] = useState<'idle' | 'adding' | 'added' | 'failed'>('idle');
  const [savedNotice, setSavedNotice] = useState(false);
  useEffect(() => {
    if (!savedNotice) return;
    const timer = window.setTimeout(() => setSavedNotice(false), 2500);
    return () => window.clearTimeout(timer);
  }, [savedNotice]);
  const { item, topicId, subjectTitle } = entry;
  const kind = itemKind(topicId) || 'book';
  const isVideo = kind === 'video';
  const isPdf = item.type === 'pdf';
  const isMedia = isVideo || isPdf;
  const Icon = icons[kind as keyof typeof icons] || BookOpen;
  const youtubeUrl = youTubeUrlFor(item);
  const alreadyMine = item.is_saved === true || state === 'added';
  const duration = videoDuration(item.duration_seconds);
  const canSave = Boolean(youtubeUrl || item.content_id);

  const open = () => {
    hapticFeedback('light');
    if (item.url && /^https?:\/\//i.test(item.url)) window.open(item.url, '_blank', 'noopener,noreferrer');
    else if (item.native_ref?.startsWith('/youtube-watch')) {
      const target = new URL(item.native_ref, window.location.origin);
      target.searchParams.set('lang', i18n.language);
      window.location.assign(target.pathname + target.search);
    } else if (item.native_ref?.startsWith('/') && !item.native_ref.startsWith('//')) navigate(item.native_ref);
  };
  const add = async () => {
    if (state === 'adding' || alreadyMine) return;
    setState('adding');
    try {
      if (item.content_id) {
        await apiClient.addUserContent(item.content_id);
      } else if (youtubeUrl) {
        const resolved = await apiClient.resolveContent(youtubeUrl);
        const id = resolved.content_id || resolved.id;
        if (!id) throw new Error('Missing content id');
        await apiClient.addUserContent(id);
      }
      setState('added'); setSavedNotice(true); onSaved?.(); hapticFeedback('success');
    } catch { setState('failed'); hapticFeedback('error'); }
  };

  return <article className={`explore-card${isMedia ? ' is-openable' : ' is-compact'}`} data-kind={kind}>
    {isMedia && <button type="button" className="explore-card-open" onClick={open}
      aria-label={`${t(isPdf ? 'explore.open' : 'learning.watch')}: ${item.title}`} />}
    <div className="explore-card-media-col">
      <div className="explore-card-media" aria-hidden="true">
        {item.image ? <img src={item.image} alt="" loading="lazy" /> : !isVideo && (isPdf ? <FileText size={28} /> : <Icon size={30} />)}
        {isVideo && (youtubeUrl ? <YouTubeThumbnailMark /> : <Play className="explore-video-play" size={28} fill="currentColor" />)}
      </div>
      {canSave && <div className="content-card-quick-actions explore-card-quick-actions">
        <button type="button" className={alreadyMine ? 'is-done' : ''}
          title={t(saveActionKey(true, state, alreadyMine))}
          aria-label={t(saveActionKey(true, state, alreadyMine))}
          disabled={state === 'adding' || alreadyMine} onClick={() => void add()}>
          <Bookmark size={17} fill={alreadyMine ? 'currentColor' : 'none'} aria-hidden="true" />
        </button>
      </div>}
    </div>
    <div className="explore-card-body">
      <div className="explore-card-labels">
        <ContentMetadataBadges language={item.language || entry.language} level={item.level}
          subject={!item.language && !entry.language ? subjectTitle : undefined}
          duration={duration || (item.estimated_read_seconds ? `~${Math.ceil(item.estimated_read_seconds / 60)}m` : null)}
          subtitles={isVideo && item.subtitles_available === true} />
        {!isMedia && <span className="explore-card-kind"><Icon size={13} aria-hidden="true" />{t(`explore.kind.${kind}`)}</span>}
      </div>
      <h3 className="explore-card-title" dir="auto">{item.title}</h3>
      {item.description && <p className="explore-card-description" dir="auto">{item.description}</p>}
      {item.creator && <span className="explore-card-creator" dir="auto">{item.creator}</span>}
      {!isMedia && <div className="explore-card-actions">
        <button type="button" className="explore-action" onClick={open}>
          {t(kind === 'course' ? 'learning.viewCourse' : kind === 'deck' ? 'learning.viewPractice' : kind === 'habit' ? 'learning.setUpRoutine' : 'explore.open')}
        </button>
      </div>}
      {item.class_offer && <p className="explore-card-offer">{item.class_offer}</p>}
      {state === 'failed' && <p role="alert" className="explore-card-error">{t('explore.addFailed')}</p>}
      {savedNotice && <p role="status" className="explore-card-saved">{t('learning.savedToLibrary')}</p>}
    </div>
  </article>;
}
