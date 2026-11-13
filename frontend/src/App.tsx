import { useEffect, useState } from 'react';
import { IntakeChat } from './components/IntakeChat';
import { HumanDeclarations } from './components/HumanDeclarations';
import { SourcePicker } from './components/SourcePicker';
import { AuthenticationStatus } from './components/AuthenticationStatus';
import {
  connectIntakeSocket,
  createSession,
  getFieldState,
  IntakeFieldState,
  IntakeResult,
  HumanFieldUpdate,
  sendMessage,
  uploadSource,
} from './services/intake';
import { AuthUser, getAuthSession } from './services/auth';

const HUMAN_ONLY_FIELD_KEYS = new Set([
  'declaration_accepted',
  'submitter_signature',
  'date_of_submission',
  'reviewer_notes',
]);

export default function App() {
  const [sessionId, setSessionId] = useState<string>();
  const [fields, setFields] = useState<IntakeFieldState[]>([]);
  const [status, setStatus] = useState('Starting secure session');
  const [error, setError] = useState('');
  const [authRequired, setAuthRequired] = useState(true);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState(
    new URLSearchParams(window.location.search).get('auth') === 'error'
      ? 'Sign-in could not be completed. Please try again.'
      : '',
  );
  const [sendOverSocket, setSendOverSocket] = useState<((text: string) => Promise<IntakeResult>)>();

  useEffect(() => {
    let active = true;
    let closeSocket: (() => void) | undefined;
    async function bootstrap() {
      let authResolved = false;
      try {
        const auth = await getAuthSession();
        authResolved = true;
        if (!active) return;
        setAuthRequired(auth.required);
        setAuthUser(auth.user);
        setAuthLoading(false);
        if (auth.required && !auth.user) {
          setStatus('Sign in required');
          return;
        }

        const session = await createSession();
        const state = await getFieldState(session.session_id);
        if (!active) return;
        setSessionId(session.session_id);
        setFields(state.sections.flatMap((section) => section.fields));
        setStatus(state.status);
        if (import.meta.env.MODE !== 'test') {
          const connection = await connectIntakeSocket(session.session_id);
          if (active && connection) {
            setSendOverSocket(() => connection.sendMessage);
            closeSocket = connection.close;
          } else {
            connection?.close();
          }
        }
      } catch {
        if (!active) return;
        if (authResolved) {
          setError('Your session could not be opened. Please try again.');
        } else {
          setAuthError('Authentication could not be verified. Please try again.');
          setAuthLoading(false);
        }
        setStatus('Unavailable');
      }
    }
    void bootstrap();
    return () => {
      active = false;
      closeSocket?.();
    };
  }, []);

  async function handleMessage(text: string): Promise<IntakeResult> {
    if (!sessionId || (authRequired && !authUser)) throw new Error('Session is unavailable.');
    setError('');
    try {
      const result = sendOverSocket ? await sendOverSocket(text) : await sendMessage(sessionId, text);
      const safeResult = filterAiUpdates(result);
      applyResult(safeResult);
      return safeResult;
    } catch {
      setSendOverSocket(undefined);
      try {
        const result = await sendMessage(sessionId, text);
        const safeResult = filterAiUpdates(result);
        applyResult(safeResult);
        return safeResult;
      } catch {
        setError('Your message could not be processed. Please try again.');
        throw new Error('Message could not be processed.');
      }
    }
  }

  async function handleSource(file: File): Promise<void> {
    if (!sessionId || (authRequired && !authUser)) return;
    setError('');
    try {
      const result = await uploadSource(sessionId, file);
      applyResult(result);
    } catch {
      setError('This source could not be processed.');
    }
  }

  function applyResult(result: IntakeResult) {
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

  return (
    <main className="workspace">
      <header className="topbar">
        <a className="brand" href="#intake" aria-label="AIMPLIFY home">
          <span className="brand-mark" aria-hidden="true">A</span>
          <span>AIMPLIFY <small>IDEA INTAKE</small></span>
        </a>
        <div className="session-status"><span className="status-dot" />{status.replace(/_/g, ' ')}</div>
        <AuthenticationStatus
          required={authRequired}
          loading={authLoading}
          user={authUser}
          error={authError}
        />
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

          <IntakeChat onSend={handleMessage} disabled={!sessionId || (authRequired && !authUser)} />
          <SourcePicker disabled={!sessionId || (authRequired && !authUser)} onSelect={handleSource} />
          {error && <p className="error-message" role="alert">{error}</p>}
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
          {sessionId && (!authRequired || authUser) && (
            <HumanDeclarations sessionId={sessionId} fields={fields} onSaved={applyHumanUpdate} />
          )}
          <div className="section-progress">
            <div className="progress-caption"><span>Submission progress</span><strong>{fields.length ? Math.round((fields.filter((field) => field.value).length / fields.length) * 100) : 0}%</strong></div>
            <div className="progress-track"><span style={{ width: `${fields.length ? (fields.filter((field) => field.value).length / fields.length) * 100 : 0}%` }} /></div>
            <p>Declaration details are recorded only from your inputs.</p>
          </div>
        </aside>
      </div>
      <footer className="page-footer"><span>IDEA INTAKE</span><span>Secure employee workspace</span></footer>
    </main>
  );
}
