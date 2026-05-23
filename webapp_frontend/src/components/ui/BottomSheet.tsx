import { useEffect, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { useModalBodyLock } from '../../hooks/useModalBodyLock';

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  showClose?: boolean;
}

export function BottomSheet({
  open,
  onClose,
  title,
  subtitle,
  children,
  showClose = true,
}: BottomSheetProps) {
  useModalBodyLock(open);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="scrim" onClick={onClose} role="presentation">
      <div
        className="sheet"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sheet-title"
      >
        <div className="handle" aria-hidden="true" />
        <div className="sheet-header">
          <div>
            <h3 id="sheet-title">{title}</h3>
            {subtitle ? <p className="sheet-sub">{subtitle}</p> : null}
          </div>
          {showClose ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close" style={{ width: 32, padding: 0 }}>
              <X size={18} />
            </button>
          ) : null}
        </div>
        <div className="body">{children}</div>
      </div>
    </div>
  );
}
