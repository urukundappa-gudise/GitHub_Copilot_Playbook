import { FormEvent, useEffect, useRef, useState } from 'react';
import { HumanFieldUpdate, IntakeFieldState, saveHumanField } from '../services/intake';

type Props = {
  sessionId: string;
  fields: IntakeFieldState[];
  onSaved: (update: HumanFieldUpdate) => void;
  disabled?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
};

const FIELD_KEYS = {
  accepted: 'declaration_accepted',
  signature: 'submitter_signature',
  date: 'date_of_submission',
  notes: 'reviewer_notes',
} as const;

function savedValues(fields: IntakeFieldState[]): Map<string, string> {
  return new Map(fields.map((field) => [field.field_key, field.value ?? '']));
}

export function HumanDeclarations({
  sessionId,
  fields,
  onSaved,
  disabled = false,
  onDirtyChange,
  onBusyChange,
}: Props) {
  const initialValues = savedValues(fields);
  const [accepted, setAccepted] = useState(
    initialValues.get(FIELD_KEYS.accepted) === 'true',
  );
  const [signature, setSignature] = useState(initialValues.get(FIELD_KEYS.signature) ?? '');
  const [date, setDate] = useState(initialValues.get(FIELD_KEYS.date) ?? '');
  const [notes, setNotes] = useState(initialValues.get(FIELD_KEYS.notes) ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const previousValues = useRef(initialValues);
  const dirty =
    accepted !== (initialValues.get(FIELD_KEYS.accepted) === 'true') ||
    signature !== (initialValues.get(FIELD_KEYS.signature) ?? '') ||
    date !== (initialValues.get(FIELD_KEYS.date) ?? '') ||
    notes !== (initialValues.get(FIELD_KEYS.notes) ?? '');

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);

  useEffect(() => {
    const currentValues = savedValues(fields);
    const previous = previousValues.current;
    if (currentValues.get(FIELD_KEYS.accepted) !== previous.get(FIELD_KEYS.accepted)) {
      setAccepted(currentValues.get(FIELD_KEYS.accepted) === 'true');
    }
    if (currentValues.get(FIELD_KEYS.signature) !== previous.get(FIELD_KEYS.signature)) {
      setSignature(currentValues.get(FIELD_KEYS.signature) ?? '');
    }
    if (currentValues.get(FIELD_KEYS.date) !== previous.get(FIELD_KEYS.date)) {
      setDate(currentValues.get(FIELD_KEYS.date) ?? '');
    }
    if (currentValues.get(FIELD_KEYS.notes) !== previous.get(FIELD_KEYS.notes)) {
      setNotes(currentValues.get(FIELD_KEYS.notes) ?? '');
    }
    previousValues.current = currentValues;
  }, [fields]);

  async function saveDeclaration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const updates = await Promise.all([
        saveHumanField(sessionId, FIELD_KEYS.accepted, accepted),
        saveHumanField(sessionId, FIELD_KEYS.signature, signature),
        saveHumanField(sessionId, FIELD_KEYS.date, date),
      ]);
      updates.forEach(onSaved);
    } catch {
      setError('Your declaration could not be saved. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  async function saveNotes(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      onSaved(await saveHumanField(sessionId, FIELD_KEYS.notes, notes));
    } catch {
      setError('Your reviewer notes could not be saved. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="human-declarations" aria-labelledby="human-declarations-title">
      <div className="human-declarations-heading">
        <p className="eyebrow">YOUR ENTRY</p>
        <h2 id="human-declarations-title">Declaration</h2>
      </div>
      <form className="human-declaration-form" onSubmit={saveDeclaration}>
        <label className="declaration-check">
          <input
            type="checkbox"
            required
            checked={accepted}
            disabled={disabled || busy}
            onChange={(event) => setAccepted(event.target.checked)}
          />
          <span>Declaration Accepted</span>
        </label>
        <label className="human-field-label" htmlFor="submitter-signature">Submitter Signature</label>
        <input
          id="submitter-signature"
          className="human-field-input"
          type="text"
          autoComplete="name"
          required
          value={signature}
          disabled={disabled || busy}
          onChange={(event) => setSignature(event.target.value)}
        />
        <label className="human-field-label" htmlFor="date-of-submission">Date of Submission</label>
        <input
          id="date-of-submission"
          className="human-field-input"
          type="date"
          required
          value={date}
          disabled={disabled || busy}
          onChange={(event) => setDate(event.target.value)}
        />
        <button className="human-save-button" type="submit" disabled={disabled || busy}>
          Save Declaration
        </button>
      </form>
      <form className="human-notes-form" onSubmit={saveNotes}>
        <label className="human-field-label" htmlFor="reviewer-notes">Additional Notes for Reviewer</label>
        <textarea
          id="reviewer-notes"
          className="human-field-input"
          rows={3}
          maxLength={4000}
          value={notes}
          disabled={disabled || busy}
          onChange={(event) => setNotes(event.target.value)}
        />
        <button className="human-save-button secondary" type="submit" disabled={disabled || busy || !notes.trim()}>
          Save Reviewer Notes
        </button>
      </form>
      {error && <p className="human-field-error" role="alert">{error}</p>}
    </section>
  );
}