import { useEffect } from 'react';

/**
 * Locks body scroll when a modal is open (e.g. overflow: hidden).
 * Prevents the page behind from scrolling when the user interacts with the modal.
 */
export function useModalBodyLock(isOpen: boolean): void {
  useEffect(() => {
    if (isOpen) {
      document.body.classList.add('modal-open');
      return () => document.body.classList.remove('modal-open');
    }
  }, [isOpen]);
}
