import { SyntheticEvent, useEffect, useRef } from 'react';

type Props = {
  open: boolean;
  onDismiss: () => void;
  onStartNew: () => void;
};

export function OutcomeDialog({ open, onDismiss, onStartNew }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const startButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      try {
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', '');
        startButtonRef.current?.focus();
      } catch {
        dialog.setAttribute('open', '');
      }
    } else if (dialog.open) {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
    }
  }, [open]);

  function dismiss(event?: SyntheticEvent<HTMLDialogElement>) {
    event?.preventDefault();
    const dialog = dialogRef.current;
    if (dialog?.open) {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
    }
    onDismiss();
  }

  return (
    <dialog
      ref={dialogRef}
      className="outcome-dialog"
      aria-labelledby="outcome-dialog-title"
      aria-describedby="outcome-dialog-description"
      aria-modal="true"
      onCancel={dismiss}
      onKeyDown={(event) => {
        if (event.key === 'Escape') dismiss(event);
      }}
    >
      <div className="outcome-dialog-content">
        <p className="eyebrow">SUBMISSION COMPLETE</p>
        <h2 id="outcome-dialog-title">Idea submitted</h2>
        <p id="outcome-dialog-description">Your idea is saved. The submitted intake is now read-only.</p>
        <p className="visually-hidden" aria-live="polite">Submission confirmed.</p>
        <div className="outcome-dialog-actions">
          <button ref={startButtonRef} type="button" className="primary-action" onClick={onStartNew}>
            Start a new idea
          </button>
          <button type="button" className="secondary-action" onClick={() => dismiss()}>
            Close
          </button>
        </div>
      </div>
    </dialog>
  );
}