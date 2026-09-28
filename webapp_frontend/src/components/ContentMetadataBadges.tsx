import { Captions, Clock3 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ContentMetadataBadgesProps {
  language?: string | null;
  level?: string | null;
  subject?: string | null;
  duration?: string | null;
  subtitles?: boolean;
}

/** The same small metadata row on Library and Explore cards. */
export function ContentMetadataBadges({ language, level, subject, duration, subtitles }: ContentMetadataBadgesProps) {
  const { t } = useTranslation();
  const code = language?.toLowerCase().split('-')[0];
  const languageName = code ? t(`learning.languages.${code}`, { defaultValue: code.toUpperCase() }) : subject;
  return <div className="content-meta-badges">
    {(languageName || level) && <span className="content-language-badge" dir="auto">
      {languageName}{languageName && level ? ' ' : ''}{level}
    </span>}
    {duration && <span className="content-duration-badge"><Clock3 size={12} aria-hidden="true" /><bdi>{duration}</bdi></span>}
    {subtitles && <span className="content-card-subtitles" title={t('content.subtitlesAvailable')}>
      <Captions size={13} aria-hidden="true" />{t('content.subtitlesAvailable')}
    </span>}
  </div>;
}
