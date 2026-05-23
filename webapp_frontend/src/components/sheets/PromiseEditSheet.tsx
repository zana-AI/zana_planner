import { useEffect, useState } from 'react';
import type { PromiseData } from '../../types';
import { apiClient } from '../../api/client';
import { InlineCalendar } from '../InlineCalendar';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';
import { PromiseDeleteConfirmModal } from '../PromiseDeleteConfirmModal';
import { VisibilityConfirmModal } from '../VisibilityConfirmModal';
import { formatPromiseText } from '../../utils/activityFormat';

interface PromiseEditSheetProps {
  open: boolean;
  promiseId: string;
  data: PromiseData;
  onClose: () => void;
  onSuccess: (message: string) => void;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return 'Not set';
  try {
    const date = new Date(`${dateStr}T00:00:00`);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return dateStr;
  }
}

export function PromiseEditSheet({ open, promiseId, data, onClose, onSuccess }: PromiseEditSheetProps) {
  const {
    text,
    hours_promised,
    visibility = 'private',
    recurring = true,
    metric_type = 'hours',
    target_value = hours_promised,
  } = data;

  const isCountBased = metric_type === 'count';
  const isClubPromise = visibility === 'clubs';

  const [editingText, setEditingText] = useState(text);
  const [editingHours, setEditingHours] = useState(hours_promised);
  const [editingTarget, setEditingTarget] = useState(target_value ?? 1);
  const [editingEndDate, setEditingEndDate] = useState(data.end_date || '');
  const [showCalendar, setShowCalendar] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [currentVisibility, setCurrentVisibility] = useState<'private' | 'public'>(
    visibility === 'public' ? 'public' : 'private',
  );
  const [currentRecurring, setCurrentRecurring] = useState(recurring);
  const [isUpdatingVisibility, setIsUpdatingVisibility] = useState(false);
  const [isUpdatingRecurring, setIsUpdatingRecurring] = useState(false);
  const [showVisibilityConfirm, setShowVisibilityConfirm] = useState(false);
  const [pendingVisibility, setPendingVisibility] = useState<'private' | 'public' | null>(null);

  useEffect(() => {
    if (!open) return;
    setEditingText(text);
    setEditingHours(hours_promised);
    setEditingTarget(target_value ?? 1);
    setEditingEndDate(data.end_date || '');
    setCurrentVisibility(visibility === 'public' ? 'public' : 'private');
    setCurrentRecurring(recurring);
    setShowCalendar(false);
  }, [open, text, hours_promised, target_value, data.end_date, visibility, recurring]);

  const handleSave = async () => {
    if (isSaving) return;
    if (!isCountBased && editingHours <= 0) {
      alert('Hours per week must be greater than 0');
      return;
    }
    if (isCountBased && editingTarget <= 0) {
      alert('Times per week must be greater than 0');
      return;
    }

    setIsSaving(true);
    try {
      const updateFields: {
        text?: string;
        hours_per_week?: number;
        target_value?: number;
        end_date?: string;
      } = {};

      if (editingText !== text) updateFields.text = editingText;
      if (!isCountBased && editingHours !== hours_promised) updateFields.hours_per_week = editingHours;
      if (isCountBased && editingTarget !== (target_value ?? 1)) updateFields.target_value = editingTarget;
      if (editingEndDate !== (data.end_date || '')) updateFields.end_date = editingEndDate || undefined;

      if (Object.keys(updateFields).length > 0) {
        await apiClient.updatePromise(promiseId, updateFields);
      }
      onSuccess('Promise updated');
      onClose();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update promise');
    } finally {
      setIsSaving(false);
    }
  };

  const handleVisibilityToggle = () => {
    if (isUpdatingVisibility || isClubPromise) return;
    setPendingVisibility(currentVisibility === 'private' ? 'public' : 'private');
    setShowVisibilityConfirm(true);
  };

  const handleVisibilityConfirm = async () => {
    if (!pendingVisibility || isUpdatingVisibility) return;
    setIsUpdatingVisibility(true);
    setShowVisibilityConfirm(false);
    try {
      await apiClient.updatePromiseVisibility(promiseId, pendingVisibility);
      setCurrentVisibility(pendingVisibility);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update visibility');
    } finally {
      setIsUpdatingVisibility(false);
      setPendingVisibility(null);
    }
  };

  const handleRecurringToggle = async () => {
    if (isUpdatingRecurring) return;
    const next = !currentRecurring;
    setIsUpdatingRecurring(true);
    try {
      await apiClient.updatePromiseRecurring(promiseId, next);
      setCurrentRecurring(next);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update repeat setting');
    } finally {
      setIsUpdatingRecurring(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (isDeleting) return;
    setIsDeleting(true);
    try {
      await apiClient.deletePromise(promiseId);
      setShowDeleteConfirm(false);
      onSuccess('Promise deleted');
      onClose();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete promise');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <>
      <BottomSheet
        open={open}
        onClose={onClose}
        title="Edit promise"
        subtitle={formatPromiseText(text)}
      >
        <div className="card-edit-form">
          <div className="card-form-group">
            <label className="card-form-label">Promise title</label>
            <input
              type="text"
              className="card-form-input"
              value={editingText}
              onChange={(e) => setEditingText(e.target.value)}
            />
          </div>

          <div className="card-form-group">
            <label className="card-form-label">{isCountBased ? 'Times per week' : 'Hours per week'}</label>
            {isCountBased ? (
              <input
                type="number"
                className="card-form-input"
                value={editingTarget}
                onChange={(e) => setEditingTarget(parseInt(e.target.value, 10) || 1)}
                min={1}
                step={1}
              />
            ) : (
              <input
                type="number"
                className="card-form-input"
                value={editingHours}
                onChange={(e) => setEditingHours(parseFloat(e.target.value) || 0)}
                min={0.1}
                step={0.1}
              />
            )}
          </div>

          <div className="card-form-group">
            <label className="card-form-label">End date</label>
            <button
              type="button"
              className="card-form-date-button"
              onClick={() => setShowCalendar(!showCalendar)}
            >
              {formatDate(editingEndDate)}
            </button>
            {showCalendar ? (
              <InlineCalendar
                selectedDate={editingEndDate || undefined}
                onDateSelect={(date) => {
                  setEditingEndDate(date);
                  setShowCalendar(false);
                }}
                minDate={data.start_date || undefined}
                onClose={() => setShowCalendar(false)}
              />
            ) : null}
          </div>

          {!isClubPromise ? (
            <div className="card-setting-row">
              <div className="card-setting-info">
                <span className="card-setting-title">Public visibility</span>
                <span className="card-setting-subtitle">
                  {currentVisibility === 'public' ? 'Visible to others' : 'Only you'}
                </span>
              </div>
              <button
                type="button"
                className={`card-switch${currentVisibility === 'public' ? ' card-switch--on' : ''}`}
                onClick={handleVisibilityToggle}
                disabled={isUpdatingVisibility}
                aria-pressed={currentVisibility === 'public'}
              >
                <span className="card-switch-track" aria-hidden="true">
                  <span className="card-switch-thumb" />
                </span>
                <span className="card-switch-label">
                  {isUpdatingVisibility ? 'Saving' : currentVisibility === 'public' ? 'Public' : 'Private'}
                </span>
              </button>
            </div>
          ) : null}

          <div className="card-setting-row">
            <div className="card-setting-info">
              <span className="card-setting-title">Repeat weekly</span>
              <span className="card-setting-subtitle">
                {currentRecurring ? 'Shows every week' : 'One-time task'}
              </span>
            </div>
            <button
              type="button"
              className={`card-switch${currentRecurring ? ' card-switch--on' : ''}`}
              onClick={handleRecurringToggle}
              disabled={isUpdatingRecurring}
              aria-pressed={currentRecurring}
            >
              <span className="card-switch-track" aria-hidden="true">
                <span className="card-switch-thumb" />
              </span>
              <span className="card-switch-label">
                {isUpdatingRecurring ? 'Saving' : currentRecurring ? 'On' : 'Off'}
              </span>
            </button>
          </div>

          <div className="card-form-button-group">
            <Button variant="primary" fullWidth onClick={handleSave} disabled={isSaving || isDeleting}>
              {isSaving ? 'Saving…' : 'Save changes'}
            </Button>
            <Button variant="secondary" fullWidth onClick={onClose} disabled={isSaving || isDeleting}>
              Cancel
            </Button>
          </div>
          <button
            type="button"
            className="card-form-button-danger"
            onClick={() => setShowDeleteConfirm(true)}
            disabled={isSaving || isDeleting}
          >
            {isDeleting ? 'Deleting…' : 'Delete promise'}
          </button>
        </div>
      </BottomSheet>

      {pendingVisibility ? (
        <VisibilityConfirmModal
          isOpen={showVisibilityConfirm}
          currentVisibility={currentVisibility}
          newVisibility={pendingVisibility}
          onConfirm={handleVisibilityConfirm}
          onCancel={() => {
            setShowVisibilityConfirm(false);
            setPendingVisibility(null);
          }}
        />
      ) : null}

      <PromiseDeleteConfirmModal
        isOpen={showDeleteConfirm}
        promiseId={promiseId}
        promiseText={formatPromiseText(text)}
        isDeleting={isDeleting}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}
