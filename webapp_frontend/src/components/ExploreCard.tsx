import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Bookmark, BookOpen, Check, Clock, GraduationCap, Layers, Repeat, Subtitles, Video } from 'lucide-react';
import { apiClient } from '../api/client';
import { useTelegramWebApp } from '../hooks/useTelegramWebApp';
import { itemKind } from '../pages/exploreVocabulary';
import { youTubeUrlFor, videoDuration, type LearningEntry } from '../utils/exploreLearning';
import { saveActionKey } from '../utils/learningActions';

const icons = { video: Video, course: GraduationCap, deck: Layers, book: BookOpen, habit: Repeat };

export function ExploreCard({ entry }: { entry: LearningEntry }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegramWebApp();
  const [state, setState] = useState<'idle' | 'adding' | 'added' | 'failed'>('idle');
  const { item, topicId, subjectTitle } = entry;
  const kind = itemKind(topicId) || 'book';
  const Icon = icons[kind as keyof typeof icons] || BookOpen;
  const youtubeUrl = youTubeUrlFor(item);
  const alreadyMine = state === 'added';
  const duration = videoDuration(item.duration_seconds);
  const subtitleLanguage = item.subtitle_language
    ? t(`learning.languages.${item.subtitle_language.toLowerCase().split('-')[0]}`, { defaultValue: item.subtitle_language }) : '';

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
    setState('adding');
    try {
      if (youtubeUrl) {
        const resolved = await apiClient.resolveContent(youtubeUrl);
        const id = resolved.content_id || resolved.id;
        if (!id) throw new Error('Missing content id');
        await apiClient.addUserContent(id);
      }
      setState('added'); hapticFeedback('success');
    } catch { setState('failed'); hapticFeedback('error'); }
  };

  return <article className={`explore-card${kind === 'video' ? '' : ' is-compact'}`} data-kind={kind}>
    <div className="explore-card-media" aria-hidden="true">
      {item.image ? <img src={item.image} alt="" loading="lazy" /> : <Icon size={30} />}
    </div>
    <div className="explore-card-body">
      <div className="explore-card-labels">
        <span className="explore-card-kind"><Icon size={13} aria-hidden="true" />{t(`explore.kind.${kind}`)}</span>
        <span dir="auto">{subjectTitle}</span>
        {item.creator && <span className="explore-card-creator" dir="auto">{item.creator}</span>}
      </div>
      <h3 className="explore-card-title" dir="auto">{item.title}</h3>
      {item.description && <p className="explore-card-description" dir="auto">{item.description}</p>}
      <div className="explore-card-footer">
      {kind === 'video' && <div className="explore-learning-meta">
        {duration && <span><Clock size={13} aria-hidden="true" /><bdi>{duration}</bdi></span>}
        {item.subtitles_available === true ? <span className="is-ready"><Subtitles size={14} aria-hidden="true" />
          {subtitleLanguage ? t('learning.subtitlesReady', { language: subtitleLanguage }) : t('learning.captionsReady')}
        </span> : <span>{t(item.subtitles_available === false ? 'learning.notCached' : 'learning.captionStatusUnknown')}</span>}
      </div>}
      <div className="explore-card-actions">
        <button type="button" className={`explore-action${kind === 'video' ? ' is-primary' : ''}`} onClick={open}>
          {t(kind === 'video' ? 'learning.watch' : kind === 'course' ? 'learning.viewCourse' : kind === 'deck' ? 'learning.viewPractice' : kind === 'habit' ? 'learning.setUpRoutine' : 'explore.open')}
        </button>
        {youtubeUrl && <button type="button" className={`explore-action explore-save${alreadyMine ? ' is-done' : ''}`}
          title={t(saveActionKey(true, state, false))}
          aria-label={t(saveActionKey(true, state, false))}
          disabled={state === 'adding' || alreadyMine} onClick={() => void add()}>
          {alreadyMine ? <Check size={18} aria-hidden="true" /> : <Bookmark size={18} aria-hidden="true" />}
        </button>}
      </div>
      </div>
      {item.class_offer && <p className="explore-card-offer">{item.class_offer}</p>}
      {state === 'failed' && <p role="alert" className="explore-card-error">{t('explore.addFailed')}</p>}
    </div>
  </article>;
}
