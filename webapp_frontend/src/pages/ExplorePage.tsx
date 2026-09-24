import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { UsersRound } from 'lucide-react';
import { apiClient } from '../api/client';
import { ExploreCard } from '../components/ExploreCard';
import type { ExploreCatalog } from '../types';
import { catalogEntries, exploreFilter, exploreFilterParams, EXPLORE_FILTERS } from '../utils/exploreLearning';
import './explore.css';

export function ExplorePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { subjectId } = useParams();
  const [params, setParams] = useSearchParams();
  const subject = subjectId || params.get('subject') || 'all';
  const filter = exploreFilter(params.get('type'));
  const [catalog, setCatalog] = useState<ExploreCatalog | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setError(false);
    apiClient.getExploreCatalog().then(data => { if (active) setCatalog(data); }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [attempt]);

  const updateFilter = (type: string, nextSubject = subject) => {
    const next = exploreFilterParams(type, nextSubject);
    if (subjectId) navigate('/explore?' + next);
    else setParams(next);
  };
  if (error) return <main className="app"><p role="alert">{t('templates.loadFailed')}</p><button className="explore-action" onClick={() => setAttempt(a => a + 1)}>{t('common.tryAgain')}</button></main>;
  if (!catalog) return <main className="app"><p role="status">{t('common.loading')}</p></main>;

  const allEntries = catalogEntries(catalog);
  const entries = allEntries.filter(e => (subject === 'all' || subject === e.subjectId) && (filter === 'all' || filter === e.topicId))
    .sort((a, b) => Number(!!b.item.starter) - Number(!!a.item.starter) || a.item.order - b.item.order);
  const showClubs = filter === 'clubs' || (filter === 'all' && subject === 'all');
  const clubs = showClubs ? catalog.clubs || [] : [];
  const visibleFilters = EXPLORE_FILTERS.filter(f => ['all', 'clubs', filter].includes(f) || allEntries.some(e => e.topicId === f));
  return <main className="app explore-page">
    <div className="explore-filter-bar">
      <label className="explore-subject-select">
        <select aria-label={t('learning.subject')} value={subject} onChange={event => updateFilter(filter === 'clubs' ? 'watch' : filter, event.target.value)}>
          <option value="all">{t('learning.allSubjects')}</option>
          {catalog.categories.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
      </label>
      <div className="explore-chips" role="group" aria-label={t('learning.contentTypes')}>
        {visibleFilters.map(f => <button type="button" key={f} className={'explore-chip' + (filter === f ? ' is-active' : '')}
          aria-pressed={filter === f} onClick={() => updateFilter(f)}>{t(f === 'all' ? 'explore.all' : f === 'clubs' ? 'community.clubs' : 'explore.topic.' + f)}</button>)}
      </div>
    </div>
    {filter === 'clubs' && <div className="explore-club-tools"><p>{t('learning.clubsHint')}</p><button type="button" className="explore-action" onClick={() => navigate('/clubs')}>{t('learning.manageClubs')}</button></div>}
    <div className="explore-list">
      {entries.map(entry => <ExploreCard key={entry.subjectId + ':' + entry.item.id} entry={entry} />)}
      {clubs.map(club => <article key={club.club_id} className="explore-card is-compact" data-kind="club">
        <div className="explore-card-media" aria-hidden="true"><UsersRound size={30} /></div>
        <div className="explore-card-body">
          <div className="explore-card-labels"><span className="explore-card-kind"><UsersRound size={13} aria-hidden="true" />{t('learning.club')}</span>{club.joined && <span>{t('learning.joinedClub')}</span>}</div>
          <h3 className="explore-card-title" dir="auto">{club.name}</h3>
          {club.description && <p className="explore-card-description" dir="auto">{club.description}</p>}
          <div className="explore-card-actions"><button type="button" className="explore-action" onClick={() => navigate('/' + (club.joined ? 'clubs' : 'c') + '/' + encodeURIComponent(club.club_id))}>{t('learning.viewClub')}</button></div>
        </div>
      </article>)}
    </div>
    {showClubs && catalog.clubs_available === false && <p role="status">{t('learning.clubsUnavailable')}</p>}
    {entries.length + clubs.length === 0 && !(showClubs && catalog.clubs_available === false) && <p className="explore-empty">{t('learning.noResults')}</p>}
  </main>;
}
