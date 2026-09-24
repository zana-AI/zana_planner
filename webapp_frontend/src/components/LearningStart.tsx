import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Languages, Plus, Repeat } from 'lucide-react';
import { apiClient } from '../api/client';
import { starterEntries, type LearningEntry } from '../utils/exploreLearning';
import { ExploreCard } from './ExploreCard';
import { ROUTINE_EXAMPLES, type RoutineDraft } from '../utils/learningActions';

export function LearningStart({ onCreateRoutine }: { onCreateRoutine: (draft?: RoutineDraft) => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [entries, setEntries] = useState<LearningEntry[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    apiClient.getExploreCatalog().then(catalog => { if (active) setEntries(starterEntries(catalog).slice(0, 2)); })
      .catch(() => undefined).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  return <section className="learning-start" aria-labelledby="learning-start-title">
    <div className="learning-start-intro">
      <h2 id="learning-start-title">{t('learning.startTitle')}</h2>
      <p>{t(entries.length > 0 ? 'learning.startWithPicks' : 'learning.startHint')}</p>
    </div>
    {entries.length > 0 ? <div className="learning-start-picks">
      <div className="learning-picks-heading"><h3>{t('learning.readyToWatch')}</h3>
        <button type="button" className="learning-browse-more" onClick={() => navigate('/explore?type=watch')}>
          {t('learning.browseMore')}<ArrowRight size={15} className="icon-directional" aria-hidden="true" />
        </button>
      </div>
      <div className="explore-list">{entries.map(entry => <ExploreCard key={entry.item.id} entry={entry} />)}</div>
    </div> : loading ? <p role="status">{t('common.loading')}</p> : <div className="learning-start-actions">
      <button type="button" className="explore-action is-primary" onClick={() => navigate('/explore?type=watch')}>{t('learning.exploreVideos')}</button>
      <button type="button" className="explore-action" onClick={() => navigate('/my-contents')}>{t('learning.openLibrary')}</button>
    </div>}
    <section className="learning-routine-card" aria-labelledby="learning-routine-title">
      <h3 id="learning-routine-title"><Repeat size={18} aria-hidden="true" />{t('learning.routineTitle')}</h3>
      <p>{t('learning.routineHint')}</p>
      <div className="learning-routine-examples">
        {ROUTINE_EXAMPLES.map(example => (
          <button type="button" key={example.id} onClick={() => onCreateRoutine({ text: t(`learning.routines.${example.id}`), hoursPerWeek: example.hoursPerWeek })}>
            <Languages size={20} aria-hidden="true" />
            <span><strong>{t(`learning.routines.${example.id}`)}</strong><small>{t('learning.minutesPerWeek', { count: example.minutes })}</small></span>
            <Plus size={16} aria-hidden="true" />
          </button>
        ))}
      </div>
      <button type="button" className="explore-action learning-custom-routine" onClick={() => onCreateRoutine()}>
        <Plus size={15} aria-hidden="true" />{t('learning.customRoutine')}
      </button>
    </section>
  </section>;
}
