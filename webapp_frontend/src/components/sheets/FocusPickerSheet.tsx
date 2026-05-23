import { useState } from 'react';
import type { PromiseData } from '../../types';
import { formatPromiseText } from '../../utils/activityFormat';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';

interface FocusPickerSheetProps {
  open: boolean;
  promises: Array<{ id: string; data: PromiseData }>;
  onClose: () => void;
  onStart: (promiseId: string, promiseText: string) => void;
}

export function FocusPickerSheet({ open, promises, onClose, onStart }: FocusPickerSheetProps) {
  const [selectedId, setSelectedId] = useState('');

  const handleStart = () => {
    const selected = promises.find((item) => item.id === selectedId);
    if (!selected) return;
    onStart(selected.id, selected.data.text);
  };

  return (
    <BottomSheet open={open} onClose={onClose} title="Start focus" subtitle="Choose a promise">
      <div className="list">
        {promises.map(({ id, data }) => (
          <button
            key={id}
            type="button"
            className={`focus-pick-row${selectedId === id ? ' is-selected' : ''}`}
            onClick={() => setSelectedId(id)}
          >
            <span className="radio" aria-hidden="true" />
            <span>
              <div className="t">{formatPromiseText(data.text)}</div>
              <div className="m">#{id}</div>
            </span>
          </button>
        ))}
      </div>
      <Button variant="primary" fullWidth onClick={handleStart} disabled={!selectedId} style={{ marginTop: 16 }}>
        Start 25-minute focus
      </Button>
    </BottomSheet>
  );
}
