import { useState, useEffect, useCallback, useImperativeHandle, forwardRef } from 'react';
import type { PlanSession, PlanSessionIn } from '../types';
import { apiClient } from '../api/client';

export interface PlanSessionsListRef {
  openAddForm: () => void;
}

interface PlanSessionsListProps {
  promiseId: string;  // user-facing promise ID (current_id)
  /** If provided, the list will use these sessions instead of fetching them. */
  externalSessions?: PlanSession[];
  /** Called whenever the sessions list changes (create / delete / update). */
  onSessionsChange?: (sessions: PlanSession[]) => void;
}

function formatPlannedStart(iso: string | null): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

const EMPTY_FORM: PlanSessionIn = {
  title: '',
  planned_start: '',
  planned_duration_min: undefined,
  notes: '',
  checklist: [],
};

export const PlanSessionsList = forwardRef<PlanSessionsListRef, PlanSessionsListProps>(
function PlanSessionsList({ promiseId, externalSessions, onSessionsChange }: PlanSessionsListProps, ref) {
  const [sessions, setSessions] = useState<PlanSession[]>(externalSessions ?? []);
  const [loading, setLoading] = useState(!externalSessions);
  const [error, setError] = useState<string | null>(null);

  // Add-session form
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<PlanSessionIn>(EMPTY_FORM);
  const [newItemText, setNewItemText] = useState('');
  const [saving, setSaving] = useState(false);

  // Expanded checklist view per session
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  // Sync external sessions if provided
  useEffect(() => {
    if (externalSessions) {
      setSessions(externalSessions);
      setLoading(false);
    }
  }, [externalSessions]);

  // Expose openAddForm via ref
  useImperativeHandle(ref, () => ({
    openAddForm: () => setShowForm(true),
  }));

  const loadSessions = useCallback(async () => {
    if (externalSessions) return; // managed by parent
    try {
      setLoading(true);
      setError(null);
      const data = await apiClient.getPlanSessions(promiseId);
      setSessions(data);
      onSessionsChange?.(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }, [promiseId, externalSessions, onSessionsChange]);

  useEffect(() => {
    if (!externalSessions) loadSessions();
  }, [loadSessions, externalSessions]);

  // ---- Session status toggle ----
  async function handleStatusToggle(session: PlanSession) {
    const next = session.status === 'done' ? 'planned' : 'done';
    try {
      const updated = await apiClient.updatePlanSessionStatus(session.id, next);
      setSessions(prev => {
        const next = prev.map(s => s.id === updated.id ? updated : s);
        onSessionsChange?.(next);
        return next;
      });
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to update status');
    }
  }

  // ---- Checklist item toggle ----
  async function handleChecklistToggle(session: PlanSession, itemId: number, done: boolean) {
    try {
      const updated = await apiClient.togglePlanChecklistItem(session.id, itemId, done);
      setSessions(prev => {
        const next = prev.map(s => s.id === updated.id ? updated : s);
        onSessionsChange?.(next);
        return next;
      });
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to update item');
    }
  }

  // ---- Delete session ----
  async function handleDelete(sessionId: number) {
    if (!confirm('Delete this session?')) return;
    try {
      await apiClient.deletePlanSession(sessionId);
      setSessions(prev => {
        const next = prev.filter(s => s.id !== sessionId);
        onSessionsChange?.(next);
        return next;
      });
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to delete session');
    }
  }

  // ---- Create session ----
  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: PlanSessionIn = {
        ...form,
        planned_start: form.planned_start || undefined,
        planned_duration_min: form.planned_duration_min || undefined,
        notes: form.notes || undefined,
        title: form.title || undefined,
      };
      const created = await apiClient.createPlanSession(promiseId, payload);
      setSessions(prev => {
        const next = [...prev, created];
        onSessionsChange?.(next);
        return next;
      });
      setForm(EMPTY_FORM);
      setNewItemText('');
      setShowForm(false);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to create session');
    } finally {
      setSaving(false);
    }
  }

  function addChecklistItem() {
    const text = newItemText.trim();
    if (!text) return;
    setForm(f => ({
      ...f,
      checklist: [...(f.checklist ?? []), { text, done: false, position: (f.checklist ?? []).length }],
    }));
    setNewItemText('');
  }

  function removeChecklistItem(idx: number) {
    setForm(f => ({ ...f, checklist: (f.checklist ?? []).filter((_, i) => i !== idx) }));
  }

  function toggleExpanded(id: number) {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // ---- Group by status ----
  const planned = sessions.filter(s => s.status === 'planned');
  const done = sessions.filter(s => s.status === 'done');
  const skipped = sessions.filter(s => s.status === 'skipped');

  function renderSession(session: PlanSession) {
    const expanded = expandedIds.has(session.id);
    const hasChecklist = session.checklist.length > 0;
    const doneCount = session.checklist.filter(i => i.done).length;

    return (
      <div
        key={session.id}
        style={{
          border: '1px solid rgba(232,238,252,0.12)',
          borderRadius: 8,
          padding: '10px 12px',
          marginBottom: 8,
          background: session.status === 'done'
            ? 'rgba(34,197,94,0.1)'
            : 'rgba(15,23,48,0.55)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {/* Title + time */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{ fontWeight: 500, fontSize: 14, color: 'var(--text)' }}>
              {session.title || 'Session'}
            </span>
            {session.planned_start && (
              <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 6 }}>
                {formatPlannedStart(session.planned_start)}
              </span>
            )}
          </div>

          {/* Duration badge */}
          {session.planned_duration_min && (
            <span style={{
              background: 'rgba(99,167,247,0.15)',
              color: 'var(--accent-hover)',
              borderRadius: 4,
              padding: '1px 6px',
              fontSize: 11,
              fontWeight: 600,
            }}>
              {session.planned_duration_min}m
            </span>
          )}

          {/* Checklist summary */}
          {hasChecklist && (
            <button
              onClick={() => toggleExpanded(session.id)}
              style={{ fontSize: 11, color: 'var(--muted)', cursor: 'pointer', background: 'none', border: 'none' }}
            >
              {doneCount}/{session.checklist.length} ✓ {expanded ? '▲' : '▼'}
            </button>
          )}

          {/* Status toggle */}
          <button
            onClick={() => handleStatusToggle(session)}
            style={{
              fontSize: 11,
              padding: '2px 8px',
              borderRadius: 4,
              border: '1px solid',
              cursor: 'pointer',
              background: session.status === 'done'
                ? 'rgba(34,197,94,0.18)'
                : 'rgba(232,238,252,0.06)',
              borderColor: session.status === 'done'
                ? 'rgba(34,197,94,0.4)'
                : 'rgba(232,238,252,0.18)',
              color: session.status === 'done' ? '#86efac' : 'var(--text)',
            }}
          >
            {session.status === 'done' ? 'Undo' : 'Mark Done'}
          </button>

          {/* Delete */}
          <button
            onClick={() => handleDelete(session.id)}
            style={{ fontSize: 12, color: '#f87171', background: 'none', border: 'none', cursor: 'pointer' }}
            title="Delete session"
          >
            ✕
          </button>
        </div>

        {/* Notes */}
        {session.notes && (
          <p style={{ fontSize: 12, color: 'var(--text)', opacity: 0.8, margin: '4px 0 0 0' }}>{session.notes}</p>
        )}

        {/* Checklist items */}
        {expanded && hasChecklist && (
          <div style={{ marginTop: 8, paddingLeft: 4 }}>
            {session.checklist.map(item => (
              <label
                key={item.id}
                style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: 4, cursor: 'pointer' }}
              >
                <input
                  type="checkbox"
                  checked={item.done}
                  onChange={e => handleChecklistToggle(session, item.id, e.target.checked)}
                />
                <span style={{ textDecoration: item.done ? 'line-through' : 'none', color: item.done ? 'var(--muted)' : 'var(--text)' }}>
                  {item.text}
                </span>
              </label>
            ))}
          </div>
        )}
      </div>
    );
  }

  function renderGroup(label: string, items: PlanSession[], accent: string) {
    if (items.length === 0) return null;
    return (
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: accent, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>
          {label} ({items.length})
        </div>
        {items.map(renderSession)}
      </div>
    );
  }

  if (loading) {
    return <div style={{ fontSize: 13, color: 'var(--muted)', padding: '8px 0' }}>Loading sessions…</div>;
  }

  return (
    <div style={{ marginTop: 12 }}>
      {error && (
        <div style={{ fontSize: 12, color: '#f87171', marginBottom: 8 }}>{error}</div>
      )}

      {sessions.length === 0 && !showForm && (
        <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 8 }}>No sessions yet.</div>
      )}

      {renderGroup('Planned', planned, 'var(--accent)')}
      {renderGroup('Done', done, '#4ade80')}
      {renderGroup('Skipped', skipped, 'var(--muted)')}

      {/* Add session form */}
      {showForm ? (
        <form
          onSubmit={handleCreate}
          style={{ border: '1px dashed rgba(99,167,247,0.3)', borderRadius: 8, padding: 12, marginTop: 8, background: 'rgba(15,23,48,0.5)' }}
        >
          <div style={{ marginBottom: 8 }}>
            <input
              placeholder="Title (optional)"
              value={form.title ?? ''}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              style={{ width: '100%', fontSize: 13, padding: '4px 8px', borderRadius: 4, border: '1px solid rgba(232,238,252,0.18)', background: 'rgba(9,15,31,0.7)', color: 'var(--text)', boxSizing: 'border-box' }}
            />
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            <input
              type="datetime-local"
              value={form.planned_start ?? ''}
              onChange={e => setForm(f => ({ ...f, planned_start: e.target.value }))}
              style={{ flex: 1, fontSize: 13, padding: '4px 8px', borderRadius: 4, border: '1px solid rgba(232,238,252,0.18)', background: 'rgba(9,15,31,0.7)', color: 'var(--text)', minWidth: 160 }}
            />
            <input
              type="number"
              placeholder="Duration (min)"
              value={form.planned_duration_min ?? ''}
              onChange={e => setForm(f => ({ ...f, planned_duration_min: e.target.value ? Number(e.target.value) : undefined }))}
              style={{ width: 130, fontSize: 13, padding: '4px 8px', borderRadius: 4, border: '1px solid rgba(232,238,252,0.18)', background: 'rgba(9,15,31,0.7)', color: 'var(--text)' }}
              min={1}
            />
          </div>
          <div style={{ marginBottom: 8 }}>
            <textarea
              placeholder="Notes (optional)"
              value={form.notes ?? ''}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              rows={2}
              style={{ width: '100%', fontSize: 13, padding: '4px 8px', borderRadius: 4, border: '1px solid rgba(232,238,252,0.18)', background: 'rgba(9,15,31,0.7)', color: 'var(--text)', resize: 'vertical', boxSizing: 'border-box' }}
            />
          </div>

          {/* Checklist builder */}
          {(form.checklist ?? []).length > 0 && (
            <div style={{ marginBottom: 6 }}>
              {(form.checklist ?? []).map((item, idx) => (
                <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: 3, color: 'var(--text)' }}>
                  <span style={{ flex: 1 }}>• {item.text}</span>
                  <button type="button" onClick={() => removeChecklistItem(idx)} style={{ color: '#f87171', background: 'none', border: 'none', cursor: 'pointer', fontSize: 12 }}>✕</button>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            <input
              placeholder="Add checklist item…"
              value={newItemText}
              onChange={e => setNewItemText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addChecklistItem(); } }}
              style={{ flex: 1, fontSize: 13, padding: '4px 8px', borderRadius: 4, border: '1px solid rgba(232,238,252,0.18)', background: 'rgba(9,15,31,0.7)', color: 'var(--text)' }}
            />
            <button type="button" onClick={addChecklistItem} style={{ fontSize: 12, padding: '4px 8px', borderRadius: 4, border: '1px solid rgba(232,238,252,0.18)', background: 'rgba(232,238,252,0.06)', color: 'var(--text)', cursor: 'pointer' }}>+ Add</button>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="submit"
              disabled={saving}
              style={{ fontSize: 13, padding: '5px 14px', borderRadius: 4, background: 'var(--accent)', color: '#fff', border: 'none', cursor: saving ? 'not-allowed' : 'pointer', fontWeight: 600 }}
            >
              {saving ? 'Saving…' : 'Save Session'}
            </button>
            <button
              type="button"
              onClick={() => { setShowForm(false); setForm(EMPTY_FORM); setNewItemText(''); }}
              style={{ fontSize: 13, padding: '5px 14px', borderRadius: 4, background: 'rgba(232,238,252,0.06)', border: '1px solid rgba(232,238,252,0.14)', color: 'var(--text)', cursor: 'pointer' }}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          onClick={() => setShowForm(true)}
          style={{
            fontSize: 13,
            color: 'var(--accent)',
            background: 'none',
            border: '1px dashed rgba(99,167,247,0.35)',
            borderRadius: 6,
            padding: '5px 12px',
            cursor: 'pointer',
            marginTop: 4,
          }}
        >
          + Add Session
        </button>
      )}
    </div>
  );
});
