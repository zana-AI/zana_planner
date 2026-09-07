import { useCallback, useEffect, useMemo, useState } from 'react';
import { FileText, Globe2, Layers3, Lock, Pencil, Plus, Search, Trash2, UsersRound, Video, X } from 'lucide-react';
import { apiClient } from '../../api/client';
import type { AdminContentClub, AdminContentItem, AdminUser, ContentVisibility } from '../../types';

interface ContentAdminTabProps {
  users: AdminUser[];
  onError: (message: string) => void;
}

type EditorDraft = {
  title: string;
  description: string;
  visibility: ContentVisibility;
  club_id: string;
};

const emptyDraft: EditorDraft = { title: '', description: '', visibility: 'private', club_id: '' };

function accessIcon(visibility: ContentVisibility) {
  if (visibility === 'public') return <Globe2 size={14} />;
  if (visibility === 'club') return <UsersRound size={14} />;
  return <Lock size={14} />;
}

function contentIcon(item: AdminContentItem) {
  if (item.kind === 'deck' || item.kind === 'challenge') return <Layers3 size={20} />;
  if (item.content_type === 'video') return <Video size={20} />;
  return <FileText size={20} />;
}

export function ContentAdminTab({ users, onError }: ContentAdminTabProps) {
  const [items, setItems] = useState<AdminContentItem[]>([]);
  const [clubs, setClubs] = useState<AdminContentClub[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [includeUsers, setIncludeUsers] = useState(false);
  const [kind, setKind] = useState<'all' | 'content' | 'deck' | 'challenge'>('all');
  const [visibility, setVisibility] = useState<'all' | ContentVisibility>('all');
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [createKind, setCreateKind] = useState<'content' | 'deck' | 'challenge'>('content');
  const [ownerId, setOwnerId] = useState('');
  const [draft, setDraft] = useState<EditorDraft>(emptyDraft);
  const [url, setUrl] = useState('');
  const [parentId, setParentId] = useState('');
  const [editing, setEditing] = useState<AdminContentItem | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [content, clubResult] = await Promise.all([
        apiClient.getAdminContent({ include_user_content: includeUsers, kind, visibility, q: debouncedQuery }),
        apiClient.getAdminContentClubs(),
      ]);
      setItems(content.items);
      setOwnerId((current) => current || content.admin_user_id);
      setClubs(clubResult.clubs);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Could not load content inventory.');
    } finally {
      setLoading(false);
    }
  }, [includeUsers, kind, visibility, debouncedQuery, onError]);

  useEffect(() => { void load(); }, [load]);

  const ownerOptions = useMemo(() => [...users].sort((a, b) => {
    const left = a.latin_name || a.first_name || a.username || a.user_id;
    const right = b.latin_name || b.first_name || b.username || b.user_id;
    return left.localeCompare(right);
  }), [users]);

  const deckParents = useMemo(
    () => items.filter((item) => item.kind === 'deck' && item.owner_user_id === ownerId),
    [items, ownerId],
  );

  const resetEditor = () => {
    setDraft(emptyDraft);
    setUrl('');
    setParentId('');
    setEditing(null);
    setShowCreate(false);
  };

  const openEdit = (item: AdminContentItem) => {
    setEditing(item);
    setDraft({
      title: item.title,
      description: item.description || '',
      visibility: item.visibility,
      club_id: item.club_id || '',
    });
    setShowCreate(false);
  };

  const saveCreate = async () => {
    setSaving(true);
    try {
      await apiClient.createAdminContent({
        kind: createKind,
        owner_user_id: ownerId || undefined,
        url: createKind === 'content' ? url.trim() : undefined,
        title: draft.title.trim() || undefined,
        description: createKind === 'challenge' ? draft.description.trim() || undefined : undefined,
        parent_id: createKind === 'deck' ? parentId || undefined : undefined,
        visibility: draft.visibility,
        club_id: draft.visibility === 'club' ? draft.club_id : undefined,
      });
      resetEditor();
      await load();
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Could not add content.');
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      await apiClient.updateAdminContent(editing.kind, editing.id, {
        title: draft.title.trim(),
        description: editing.kind !== 'deck' ? draft.description.trim() || null : undefined,
        visibility: draft.visibility,
        club_id: draft.visibility === 'club' ? draft.club_id : null,
      });
      resetEditor();
      await load();
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Could not update content.');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item: AdminContentItem) => {
    const detail = item.kind === 'deck'
      ? `This permanently removes “${item.title}”, its sub-decks, cards, and review history.`
      : item.kind === 'challenge'
        ? `This permanently removes “${item.title}”, its quiz decks, questions, and ${item.user_count} participant record${item.user_count === 1 ? '' : 's'}.`
      : `This permanently removes “${item.title}” from ${item.user_count} user librar${item.user_count === 1 ? 'y' : 'ies'} and deletes its activity.`;
    if (!window.confirm(`${detail}\n\nThis cannot be undone. Continue?`)) return;
    try {
      await apiClient.deleteAdminContent(item.kind, item.id);
      setItems((current) => current.filter((candidate) => candidate.id !== item.id));
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Could not remove content.');
    }
  };

  const editor = (mode: 'create' | 'edit') => (
    <section className="admin-content-editor">
      <div className="admin-content-editor-head">
        <div>
          <h3>{mode === 'create' ? 'Add content' : 'Edit content'}</h3>
          <p>{mode === 'create' ? 'Add a link or create a flashcard deck for any user.' : editing?.path || editing?.title}</p>
        </div>
        <button className="admin-icon-button" onClick={resetEditor} aria-label="Close editor"><X size={18} /></button>
      </div>

      {mode === 'create' && (
        <div className="admin-content-segmented">
          <button className={createKind === 'content' ? 'active' : ''} onClick={() => setCreateKind('content')}>Video / document</button>
          <button className={createKind === 'deck' ? 'active' : ''} onClick={() => setCreateKind('deck')}>Flashcard deck</button>
          <button className={createKind === 'challenge' ? 'active' : ''} onClick={() => setCreateKind('challenge')}>Quiz</button>
        </div>
      )}

      <div className="admin-content-form-grid">
        {mode === 'create' && (
          <label>Owner<select value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>
            {ownerOptions.map((user) => <option key={user.user_id} value={user.user_id}>{user.latin_name || user.first_name || user.username || user.user_id}</option>)}
          </select></label>
        )}
        {mode === 'create' && createKind === 'content' && (
          <label className="wide">URL<input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://youtube.com/watch?v=…" /></label>
        )}
        <label>{mode === 'create' && createKind === 'content' ? 'Title override (optional)' : 'Name'}
          <input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
        </label>
        {mode === 'create' && createKind === 'challenge' && (
          <label className="wide">Description<textarea rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
        )}
        {mode === 'edit' && editing?.kind !== 'deck' && (
          <label className="wide">Description<textarea rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
        )}
        {mode === 'create' && createKind === 'deck' && (
          <label>Parent deck (optional)<select value={parentId} onChange={(event) => setParentId(event.target.value)}>
            <option value="">Top level</option>
            {deckParents.map((deck) => <option key={deck.id} value={deck.id}>{deck.path || deck.title}</option>)}
          </select></label>
        )}
        <label>Access<select value={draft.visibility} onChange={(event) => setDraft({ ...draft, visibility: event.target.value as ContentVisibility, club_id: event.target.value === 'club' ? draft.club_id : '' })}>
          <option value="private">Private</option><option value="club">Club</option><option value="public">Public</option>
        </select></label>
        {draft.visibility === 'club' && (
          <label>Club<select value={draft.club_id} onChange={(event) => setDraft({ ...draft, club_id: event.target.value })}>
            <option value="">Choose a club…</option>
            {clubs.map((club) => <option key={club.club_id} value={club.club_id}>{club.name}</option>)}
          </select></label>
        )}
      </div>
      <button className="admin-content-primary" disabled={saving || !draft.title.trim() && (createKind !== 'content' || mode === 'edit') || draft.visibility === 'club' && !draft.club_id || mode === 'create' && createKind === 'content' && !url.trim()} onClick={mode === 'create' ? saveCreate : saveEdit}>
        {saving ? 'Saving…' : mode === 'create' ? 'Add' : 'Save changes'}
      </button>
    </section>
  );

  return (
    <div className="admin-content-tab">
      <header className="admin-content-header">
        <div><h2>Content control</h2><p>Manage ownership, access, names, and removal across the catalog and decks.</p></div>
        <button className="admin-content-primary" onClick={() => { resetEditor(); setShowCreate(true); }}><Plus size={17} /> Add</button>
      </header>

      {(showCreate || editing) && editor(showCreate ? 'create' : 'edit')}

      <div className="admin-content-toolbar">
        <label className="admin-content-search"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, URL, or deck path" /></label>
        <select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}><option value="all">All types</option><option value="content">Videos & documents</option><option value="deck">Flashcard decks</option><option value="challenge">Quizzes & challenges</option></select>
        <select value={visibility} onChange={(event) => setVisibility(event.target.value as typeof visibility)}><option value="all">All access</option><option value="private">Private</option><option value="club">Club</option><option value="public">Public</option></select>
        <label className="admin-content-toggle"><input type="checkbox" checked={includeUsers} onChange={(event) => setIncludeUsers(event.target.checked)} /><span>Include user-owned</span></label>
      </div>

      <div className="admin-content-count">{loading ? 'Loading…' : `${items.length} item${items.length === 1 ? '' : 's'}`}</div>
      {!loading && items.length === 0 && <div className="admin-empty-state">No content matches these filters.</div>}
      <div className="admin-content-list">
        {items.map((item) => (
          <article className="admin-content-row" key={`${item.kind}:${item.id}`}>
            <div className={`admin-content-kind-icon ${item.kind}`}>{contentIcon(item)}</div>
            <div className="admin-content-main">
              <div className="admin-content-title-line"><strong>{item.title}</strong><span className={`admin-content-access ${item.visibility}`}>{accessIcon(item.visibility)} {item.visibility === 'club' ? item.club_name || 'Club' : item.visibility}</span></div>
              <div className="admin-content-meta">
                <span>{item.kind === 'deck' ? item.path || 'Flashcard deck' : item.kind === 'challenge' ? `Quiz · ${item.content_type || 'challenge'}` : `${item.provider || item.content_type || 'Content'}`}</span>
                <span>Owner: {item.owner_name || item.owner_user_id || 'System'}</span>
                <span>{item.kind === 'deck' ? `${item.item_count} cards` : item.kind === 'challenge' ? `${item.item_count} questions · ${item.user_count} players` : `${item.user_count} libraries`}</span>
              </div>
            </div>
            <div className="admin-content-actions">
              <button onClick={() => openEdit(item)} aria-label={`Edit ${item.title}`}><Pencil size={16} /></button>
              <button className="danger" onClick={() => void remove(item)} aria-label={`Delete ${item.title}`}><Trash2 size={16} /></button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
