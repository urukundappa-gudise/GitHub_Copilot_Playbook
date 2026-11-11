import { useEffect, useRef, useState } from 'react';
import { IntakeChat } from './components/IntakeChat';
import { HumanDeclarations } from './components/HumanDeclarations';
import { OutcomeDialog } from './components/OutcomeDialog';
import { SafetyDenialBanner } from './components/SafetyDenialBanner';
import { SourcePicker } from './components/SourcePicker';
import {
  connectIntakeSocket,
  createSession,
  getFieldState,
  IntakeServiceError,
  IntakeProtocolError,
  IntakeTransportError,
  IntakeFieldState,
  IntakeResult,
  HumanFieldUpdate,
  SubmissionReadiness,
  SubmissionReceipt,
  SafetyNotice,
  submitSession,
  isSupportedSource,
  sendMessage,
  uploadSource,
} from './services/intake';

const HUMAN_ONLY_FIELD_KEYS = new Set([
  'declaration_accepted',
  'submitter_signature',
  'date_of_submission',
  'reviewer_notes',
]);

export default function App() {
  type Lifecycle = 'editing' | 'submitting' | 'outcome_unknown' | 'confirmed' | 'starting_fresh' | 'fresh_start_failed';
  type NoticeEntry = {
    key: string;
    session_id: string;
    request_id: string;
    generation: number;
    notice: SafetyNotice;
    initiatingControl: HTMLElement | null;
  };

  const [sessionId, setSessionId] = useState<string>();
  const [fields, setFields] = useState<IntakeFieldState[]>([]);
  const [status, setStatus] = useState('Starting secure session');
  const [error, setError] = useState('');
  const [sendOverSocket, setSendOverSocket] = useState<((text: string, requestId?: string) => Promise<IntakeResult>)>();
  const [readiness, setReadiness] = useState<SubmissionReadiness>();
  const [receipt, setReceipt] = useState<SubmissionReceipt>();
  const [lifecycle, setLifecycle] = useState<Lifecycle>('editing');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [activeOperations, setActiveOperations] = useState(0);
  const [declarationDirty, setDeclarationDirty] = useState(false);
  const [declarationBusy, setDeclarationBusy] = useState(false);
  const [generation, setGeneration] = useState(0);
  const [nextSessionId, setNextSessionId] = useState<string>();
  const [notices, setNotices] = useState<NoticeEntry[]>([]);
  const [correctionTarget, setCorrectionTarget] = useState<string | null>(null);
  const summaryStartRef = useRef<HTMLButtonElement>(null);
  const closeSocketRef = useRef<(() => void) | undefined>(undefined);
  const generationRef = useRef(0);
  const seenNoticeKeysRef = useRef(new Set<string>());

  useEffect(() => {
    let active = true;
    createSession()
      .then(async (session) => {
        const state = await getFieldState(session.session_id);
        if (!active) return;
        setSessionId(session.session_id);
        setFields(state.sections.flatMap((section) => section.fields));
        setReadiness(state.readiness);
        setStatus(state.status);
        if (import.meta.env.MODE !== 'test') {
          const connection = await connectIntakeSocket(session.session_id);
          if (active && connection) {
            setSendOverSocket(() => connection.sendMessage);
            closeSocketRef.current = connection.close;
          } else {
            connection?.close();
          }
        }
      })
      .catch(() => {
        if (active) {
          setError('Your session could not be opened. Please try again.');
          setStatus('Unavailable');
        }
      });
    return () => {
      active = false;
      closeSocketRef.current?.();
    };
  }, []);

  useEffect(() => {
    if (receipt && lifecycle === 'confirmed' && !dialogOpen) {
      summaryStartRef.current?.focus();
    }
  }, [dialogOpen, lifecycle, receipt]);

  async function handleMessage(text: string): Promise<IntakeResult> {
    if (!sessionId) throw new Error('Session is unavailable.');
    const requestId = crypto.randomUUID();
    const linkedNotice = correctionTarget;
    const initiatingControl = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setCorrectionTarget(null);
    setActiveOperations((count) => count + 1);
    setError('');
    try {
      const result = sendOverSocket
        ? await sendOverSocket(text, requestId)
        : await sendMessage(sessionId, text, requestId);
      const safeResult = filterAiUpdates(result);
      applyResult(safeResult, linkedNotice, initiatingControl);
      return safeResult;
    } catch (error) {
      if (!(error instanceof IntakeTransportError)) {
        if (error instanceof IntakeServiceError || error instanceof IntakeProtocolError) throw error;
        throw error;
      }
      setSendOverSocket(undefined);
      try {
        const result = await sendMessage(sessionId, text, requestId);
        const safeResult = filterAiUpdates(result);
        applyResult(safeResult, linkedNotice, initiatingControl);
        return safeResult;
      } catch {
        setError('Your message could not be processed. Please try again.');
        throw new Error('Message could not be processed.');
      }
    } finally {
      setActiveOperations((count) => Math.max(0, count - 1));
    }
  }

  async function handleSource(file: File): Promise<void> {
    if (!sessionId) return;
    if (!isSupportedSource(file)) {
      setError('This source could not be processed.');
      return;
    }
    const requestId = crypto.randomUUID();
    const linkedNotice = correctionTarget;
    const initiatingControl = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setCorrectionTarget(null);
    setActiveOperations((count) => count + 1);
    setError('');
    try {
      const result = await uploadSource(sessionId, file, requestId);
      applyResult(result, linkedNotice, initiatingControl);
    } catch {
      setError('This source could not be processed.');
    } finally {
      setActiveOperations((count) => Math.max(0, count - 1));
    }
  }

  function applyResult(
    result: IntakeResult,
    linkedNotice: string | null = null,
    initiatingControl: HTMLElement | null = null,
  ) {
    if (generationRef.current !== generation) return;
    setStatus(result.status);
    setFields((current) => {
      const next = new Map(current.map((field) => [field.field_key, field]));
      for (const update of result.field_updates) {
        if (HUMAN_ONLY_FIELD_KEYS.has(update.field_key)) continue;
        const existing = next.get(update.field_key);
        if (existing) next.set(update.field_key, { ...existing, value: update.value, origin: update.origin });
      }
      return [...next.values()];
    });
    if (
      linkedNotice &&
      result.field_updates.length > 0 &&
      Object.prototype.hasOwnProperty.call(result, 'safety_notice') &&
      result.safety_notice === null
    ) {
      setNotices((current) => current.filter((entry) => entry.key !== linkedNotice));
    }
    if (result.safety_notice) {
      const notice = result.safety_notice;
      const noticeKey = `${generation}:${sessionId}:${result.request_id}`;
      if (!seenNoticeKeysRef.current.has(noticeKey)) {
        seenNoticeKeysRef.current.add(noticeKey);
        setNotices((current) => [...current, {
          key: noticeKey,
          session_id: sessionId ?? '',
          request_id: result.request_id,
          generation,
          notice,
          initiatingControl,
        }]);
      }
    }
  }

  function dismissNotice(key: string) {
    const entry = notices.find((item) => item.key === key);
    const focusWasInside = document.activeElement instanceof HTMLElement &&
      document.activeElement.closest(`[data-notice-key="${key}"]`) !== null;
    seenNoticeKeysRef.current.add(key);
    setNotices((current) => current.filter((item) => item.key !== key));
    setCorrectionTarget((current) => current === key ? null : current);
    if (focusWasInside) {
      window.requestAnimationFrame(() => {
        if (entry?.initiatingControl?.isConnected) entry.initiatingControl.focus();
        else document.getElementById('intake-message')?.focus();
      });
    }
  }

  function selectCorrection(key: string) {
    setCorrectionTarget(key);
    document.getElementById('intake-message')?.focus();
  }

  function cancelCorrection() {
    const selected = correctionTarget;
    setCorrectionTarget(null);
    window.requestAnimationFrame(() => {
      const selectedBanner = [...document.querySelectorAll<HTMLElement>('[data-notice-key]')]
        .find((banner) => banner.dataset.noticeKey === selected);
      const correctionButton = selectedBanner?.querySelector<HTMLButtonElement>('[data-correction-action]');
      if (correctionButton?.isConnected) correctionButton.focus();
      else document.getElementById('intake-message')?.focus();
    });
  }

  function filterAiUpdates(result: IntakeResult): IntakeResult {
    return {
      ...result,
      field_updates: result.field_updates.filter(
        (update) => !HUMAN_ONLY_FIELD_KEYS.has(update.field_key),
      ),
    };
  }

  function applyHumanUpdate(update: HumanFieldUpdate) {
    setFields((current) => current.map((field) => (
      field.field_key === update.field_key
        ? { ...field, value: update.value, origin: update.origin }
        : field
    )));
  }

  async function submitIdea() {
    if (!sessionId || lifecycle !== 'editing') return;
    if (declarationDirty) {
      setError('Save your declaration and notes before submitting.');
      return;
    }
    if (declarationBusy) {
      setError('Wait for your declaration save to finish before submitting.');
      return;
    }
    if (activeOperations > 0) {
      setError('Wait for active messages, uploads, and saves to finish before submitting.');
      return;
    }
    setLifecycle('submitting');
    setError('');
    let current;
    try {
      current = await getFieldState(sessionId);
      setReadiness(current.readiness);
    } catch {
      setError('The current submission readiness could not be checked. Try again before submitting.');
      setLifecycle('editing');
      return;
    }
    if (!current.readiness.ready) {
      const fieldsToFix = [...current.readiness.missing_fields, ...current.readiness.invalid_fields];
      setError(fieldsToFix.length ? `Complete or correct: ${fieldsToFix.join(', ')}.` : 'Complete all required information before submitting.');
      setLifecycle('editing');
      return;
    }
    try {
      const result = await submitSession(sessionId);
      setReceipt(result);
      setStatus(result.status);
      setLifecycle('confirmed');
      setDialogOpen(true);
    } catch (submitError) {
      if (submitError instanceof IntakeServiceError && submitError.code === 'SUBMISSION_INCOMPLETE') {
        setReadiness({
          ready: false,
          missing_fields: submitError.missing_fields,
          invalid_fields: submitError.invalid_fields,
        });
        setError('Complete or correct the required information and save your declaration before submitting.');
        setLifecycle('editing');
        return;
      }
      setError('The submission result is not yet known. Check its status before continuing.');
      setLifecycle('outcome_unknown');
    }
  }

  async function recoverSubmission() {
    if (!sessionId || lifecycle !== 'outcome_unknown') return;
    setError('');
    try {
      const current = await getFieldState(sessionId);
      setReadiness(current.readiness);
      if (current.status === 'submitted' && current.submitted_at) {
        const confirmed = {
          session_id: sessionId,
          status: 'submitted' as const,
          submitted_at: current.submitted_at,
        };
        setReceipt(confirmed);
        setStatus(confirmed.status);
        setLifecycle('confirmed');
        setDialogOpen(true);
        return;
      }
      setLifecycle('editing');
      setError('The idea is still in progress. You can retry Submit for this same idea.');
    } catch {
      setError('The submission status could not be checked. Retry the status check for this same idea.');
    }
  }

  async function startNewIdea() {
    if (lifecycle !== 'confirmed' && lifecycle !== 'fresh_start_failed') return;
    setLifecycle('starting_fresh');
    setDialogOpen(false);
    setError('');
    closeSocketRef.current?.();
    closeSocketRef.current = undefined;
    setSendOverSocket(undefined);
    try {
      let candidateSessionId = nextSessionId;
      if (!candidateSessionId) {
        const nextSession = await createSession();
        candidateSessionId = nextSession.session_id;
        setNextSessionId(candidateSessionId);
      }
      const nextState = await getFieldState(candidateSessionId);
      let nextConnection: Awaited<ReturnType<typeof connectIntakeSocket>> = null;
      if (import.meta.env.MODE !== 'test') {
        nextConnection = await connectIntakeSocket(candidateSessionId);
      }
      setSessionId(candidateSessionId);
      setFields(nextState.sections.flatMap((section) => section.fields));
      setReadiness(nextState.readiness);
      setStatus(nextState.status);
      setReceipt(undefined);
      setNextSessionId(undefined);
      setGeneration((current) => {
        const next = current + 1;
        generationRef.current = next;
        seenNoticeKeysRef.current.clear();
        return next;
      });
      setActiveOperations(0);
      setDeclarationDirty(false);
      setDeclarationBusy(false);
      setNotices([]);
      setCorrectionTarget(null);
      setError('');
      if (nextConnection) {
        setSendOverSocket(() => nextConnection.sendMessage);
        closeSocketRef.current = nextConnection.close;
      }
      setLifecycle('editing');
      window.requestAnimationFrame(() => document.getElementById('intake-message')?.focus());
    } catch {
      setLifecycle('fresh_start_failed');
      setError('Your submitted idea is saved, but a new idea could not be prepared. Retry setup to continue.');
    }
  }

  function dismissConfirmation() {
    setDialogOpen(false);
  }

  function assertNever(value: never): never {
    throw new Error(`Unsupported lifecycle state: ${value}`);
  }

  function isFrozenLifecycle(value: Lifecycle): boolean {
    switch (value) {
      case 'editing':
        return false;
      case 'submitting':
      case 'outcome_unknown':
      case 'confirmed':
      case 'starting_fresh':
      case 'fresh_start_failed':
        return true;
      default:
        return assertNever(value);
    }
  }

  const selectedNotice = notices.find((entry) => entry.key === correctionTarget);
  const frozen = isFrozenLifecycle(lifecycle);

  return (
    <main className="workspace">
      <header className="topbar">
        <a className="brand" href="#intake" aria-label="AIMPLIFY home">
          <span className="brand-mark" aria-hidden="true">A</span>
          <span>AIMPLIFY <small>IDEA INTAKE</small></span>
        </a>
        <div className="session-status"><span className="status-dot" />{status.replace(/_/g, ' ')}</div>
      </header>

      <div className="work-area" id="intake">
        <section className="conversation-column" aria-label="Idea conversation">
          <div className="conversation-heading">
            <div>
              <p className="eyebrow">NEW SUBMISSION</p>
              <h1>Tell us about your idea</h1>
              <p className="subheading">Start with the problem you want to solve. Add a document or audio note whenever it helps.</p>
            </div>
            <span className="step-marker"><span>01</span> / 03</span>
          </div>

          <IntakeChat key={`chat-${generation}`} onSend={handleMessage} disabled={!sessionId || frozen} />
          <SourcePicker key={`source-${generation}`} disabled={!sessionId || frozen} onSelect={handleSource} />
          {error && <p className="error-message" role="alert">{error}</p>}
          {notices.map((entry) => (
            <SafetyDenialBanner
              key={entry.key}
              noticeKey={entry.key}
              notice={entry.notice}
              onDismiss={() => dismissNotice(entry.key)}
              onCorrect={() => selectCorrection(entry.key)}
            />
          ))}
          {correctionTarget && (
            <div className="correction-selection" role="status">
              <span>
                Correcting the selected rejected input: {selectedNotice?.notice.reasons.join(', ') || 'detail unavailable'}.
              </span>
              <button type="button" className="secondary-action" onClick={cancelCorrection}>
                Cancel correction
              </button>
            </div>
          )}
          {lifecycle === 'outcome_unknown' && (
            <button type="button" className="secondary-action" onClick={recoverSubmission}>
              Check submission status
            </button>
          )}
          {receipt && lifecycle === 'confirmed' && !dialogOpen && (
            <section className="submitted-summary" aria-labelledby="submitted-summary-title">
              <h2 id="submitted-summary-title">Idea submitted</h2>
              <p>This intake is frozen. Your submitted idea remains saved.</p>
              <button ref={summaryStartRef} type="button" className="primary-action" onClick={startNewIdea}>
                Start a new idea
              </button>
            </section>
          )}
          {lifecycle === 'fresh_start_failed' && (
            <button type="button" className="primary-action" onClick={startNewIdea}>
              Retry new idea setup
            </button>
          )}
          <button
            type="button"
            className="primary-action submit-action"
            disabled={!sessionId || !readiness || lifecycle !== 'editing' || activeOperations > 0 || declarationBusy}
            onClick={submitIdea}
          >
            Submit idea
          </button>
          <p className="privacy-note"><span aria-hidden="true">*</span> Source files and conversation text are processed temporarily.</p>
        </section>

        <aside className="details-column" aria-label="Submission details">
          <div className="details-title">
            <div>
              <p className="eyebrow">LIVE INTAKE</p>
              <h2>Captured details</h2>
            </div>
            <span className="count-badge">{fields.filter((field) => field.value).length} / {fields.length || 27}</span>
          </div>
          {fields.length ? (
            <div className="field-list">
              {fields.filter((field) => field.value && !field.human_only).map((field) => (
                <div className="field-row" key={field.field_key}>
                  <span>{field.field_key.replace(/_/g, ' ')}</span>
                  <strong>{field.value}</strong>
                </div>
              ))}
              {!fields.some((field) => field.value) && <p className="empty-state">Your accepted details will appear here as you go.</p>}
            </div>
          ) : <p className="empty-state">Preparing your submission…</p>}
          {sessionId && (
            <HumanDeclarations
              key={`declarations-${generation}`}
              sessionId={sessionId}
              fields={fields}
              onSaved={applyHumanUpdate}
              disabled={frozen}
              onDirtyChange={setDeclarationDirty}
              onBusyChange={setDeclarationBusy}
            />
          )}
          <div className="section-progress">
            <div className="progress-caption"><span>Submission progress</span><strong>{fields.length ? Math.round((fields.filter((field) => field.value).length / fields.length) * 100) : 0}%</strong></div>
            <div className="progress-track"><span style={{ width: `${fields.length ? (fields.filter((field) => field.value).length / fields.length) * 100 : 0}%` }} /></div>
            <p>Declaration details are recorded only from your inputs.</p>
          </div>
        </aside>
      </div>
      <footer className="page-footer"><span>IDEA INTAKE</span><span>Secure employee workspace</span></footer>
      {receipt && (
        <OutcomeDialog open={dialogOpen} onDismiss={dismissConfirmation} onStartNew={startNewIdea} />
      )}
    </main>
  );
}
