import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import type { PromiseData } from '../../types';
import { formatPromiseText } from '../../utils/activityFormat';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';

interface EditPromiseResult {
  updates?: Partial<PromiseData>;
  deleted?: boolean;
  message: string;
}

interface EditPromiseSheetProps {
  open: boolean;
  promiseId: string;
  data: PromiseData;
  mockMode: boolean;
  onClose: () => void;
  onSaved: (result: EditPromiseResult) => void;
}

export function EditPromiseSheet({
  open,
  promiseId,
  data,
  mockMode,
  onClose,
  onSaved,
}: EditPromiseSheetProps) {
  const isCountBased = data.metric_type === 'count';
  const initialTarget = isCountBased ? data.target_value ?? 1 : data.hours_promised;
  const [title, setTitle] = useState(data.text);
  const [target, setTarget] = useState(initialTarget);
  const [endDate, setEndDate] = useState(data.end_date || '');
  const [visibility, setVisibility] = useState<'private' | 'public'>(
    data.visibility === 'public' ? 'public' : 'private',
  );
  const [recurring, setRecurring] = useState(data.recurring !== false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle(data.text);
    setTarget(isCountBased ? data.target_value ?? 1 : data.hours_promised);
    setEndDate(data.end_date || '');
    setVisibility(data.visibility === 'public' ? 'public' : 'private');
    setRecurring(data.recurring !== false);
  }, [data, isCountBased, open]);

  const targetLabel = isCountBased ? 'Times per week' : 'Hours per week';
  const normalizedTitle = title.trim();
  const canSave = useMemo(() => normalizedTitle.length > 0 && target > 0, [normalizedTitle, target]);

  const handleSave = async () => {
    if (!canSave || saving || deleting) return;
    setSaving(true);

    const updates: Partial<PromiseData> = {
      text: normalizedTitle,
      visibility,
      recurring,
      end_date: endDate || undefined,
    };
    if (isCountBased) {
      updates.target_value = target;
    } else {
      updates.hours_promised = target;
      updates.target_value = target;
    }

    try {
      if (!mockMode) {
        const updateFields: { text?: string; hours_per_week?: number; target_value?: number; end_date?: string } = {};
        if (normalizedTitle !== data.text) updateFields.text = normalizedTitle;
        if (isCountBased && target !== (data.target_value ?? 1)) updateFields.target_value = target;
        if (!isCountBased && target !== data.hours_promised) updateFields.hours_per_week = target;
        if (endDate !== (data.end_date || '')) updateFields.end_date = endDate || undefined;

        if (Object.keys(updateFields).length > 0) {
          await apiClient.updatePromise(promiseId, updateFields);
        }
        if (visibility !== (data.visibility === 'public' ? 'public' : 'private')) {
          await apiClient.updatePromiseVisibility(promiseId, visibility);
        }
        if (recurring !== (data.recurring !== false)) {
          await apiClient.updatePromiseRecurring(promiseId, recurring);
        }
      }

      onSaved({ updates, message: 'Promise updated' });
      onClose();
    } catch (err) {
      console.error('Failed to update promise:', err);
      alert(err instanceof Error ? err.message : 'Failed to update promise');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (saving || deleting) return;
    if (!window.confirm(`Delete "${formatPromiseText(data.text)}"?`)) return;

    setDeleting(true);
    try {
      if (!mockMode) {
        await apiClient.deletePromise(promiseId);
      }
      onSaved({ deleted: true, message: 'Promise deleted' });
      onClose();
    } catch (err) {
      console.error('Failed to delete promise:', err);
      alert(err instanceof Error ? err.message : 'Failed to delete promise');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <BottomSheet open={open} onClose={onClose} title="Edit promise" subtitle={formatPromiseText(data.text)}>
      <div className="edit-sheet-form">
        <div className="field-row">
          <label htmlFor="edit-promise-title">Promise title</label>
          <input
            id="edit-promise-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="What are you committing to?"
          />
        </div>

        <div className="edit-sheet-grid">
          <div className="field-row">
            <label htmlFor="edit-promise-target">{targetLabel}</label>
            <input
              id="edit-promise-target"
              type="number"
              min={isCountBased ? 1 : 0.1}
              step={isCountBased ? 1 : 0.1}
              value={target}
              onChange={(event) => setTarget(Number(event.target.value) || 0)}
            />
          </div>
          <div className="field-row">
            <label htmlFor="edit-promise-end">End date</label>
            <input
              id="edit-promise-end"
              type="date"
              value={endDate}
              min={data.start_date}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </div>
        </div>

        <div className="edit-sheet-grid">
          <label className="edit-sheet-toggle">
            <span>
              <strong>Public visibility</strong>
              <span>{visibility === 'public' ? 'Visible to others' : 'Only visible to you'}</span>
            </span>
            <input
              type="checkbox"
              checked={visibility === 'public'}
              onChange={(event) => setVisibility(event.target.checked ? 'public' : 'private')}
            />
          </label>
          <label className="edit-sheet-toggle">
            <span>
              <strong>Repeat weekly</strong>
              <span>{recurring ? 'Tracked every week' : 'One-time task'}</span>
            </span>
            <input
              type="checkbox"
              checked={recurring}
              onChange={(event) => setRecurring(event.target.checked)}
            />
          </label>
        </div>

        <div className="edit-sheet-actions">
          <div className="edit-sheet-actions-main">
            <Button variant="primary" onClick={handleSave} disabled={!canSave || saving || deleting}>
              {saving ? 'Saving...' : 'Save'}
            </Button>
            <Button variant="secondary" onClick={onClose} disabled={saving || deleting}>
              Cancel
            </Button>
          </div>
          <Button variant="danger" onClick={handleDelete} disabled={saving || deleting}>
            {deleting ? 'Deleting...' : 'Delete promise'}
          </Button>
        </div>
      </div>
    </BottomSheet>
  );
}
