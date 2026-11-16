import { FormEvent, useEffect, useRef, useState } from 'react';
import { IntakeResult } from '../services/intake';
import { ClarificationPrompt } from './ClarificationPrompt';

type Props = {
  disabled: boolean;
  onSend: (text: string) => Promise<IntakeResult>;
};

export function IntakeChat({ disabled, onSend }: Props) {
  const [text, setText] = useState('');
  const [turns, setTurns] = useState<Array<{ role: 'you' | 'intake'; text: string; clarification?: boolean }>>([]);
  const [busy, setBusy] = useState(false);
  const mounted = useRef(false);
  const sending = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = text.trim();
    if (!message || disabled || sending.current) return;
    sending.current = true;
    setText('');
    setTurns((current) => [...current, { role: 'you', text: message }]);
    setBusy(true);
    try {
      const result = await onSend(message);
      if (!mounted.current) return;
      const updates = result.field_updates.map((update) => update.value);
      const reply = result.clarification?.question ?? (updates.length ? 'I have captured the safe details for your submission.' : 'Tell me a little more about the idea.');
      setTurns((current) => [
        ...current,
        ...updates.map((value) => ({ role: 'intake' as const, text: value })),
        { role: 'intake', text: reply, clarification: Boolean(result.clarification) },
      ]);
    } catch {
      if (mounted.current) setTurns((current) => [...current, { role: 'intake', text: 'I could not process that turn. Please try again.' }]);
    } finally {
      sending.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-feed" aria-live="polite" aria-label="Conversation">
        {!turns.length && (
          <div className="welcome-turn">
            <span className="assistant-mark" aria-hidden="true">A</span>
            <div><span className="speaker-label">AIMPLIFY INTAKE</span><p>What challenge or opportunity should this idea address?</p></div>
          </div>
        )}
        {turns.map((turn, index) => (
          <div className={`chat-turn ${turn.role}`} key={`${turn.role}-${index}`}>
            {turn.role === 'intake' && <span className="assistant-mark" aria-hidden="true">A</span>}
            <div className="turn-content">
              {turn.role === 'intake' && <span className="speaker-label">AIMPLIFY INTAKE</span>}
              {turn.clarification ? <ClarificationPrompt question={turn.text} /> : <p>{turn.text}</p>}
            </div>
          </div>
        ))}
        {busy && <div className="working-indicator" role="status">Reviewing your message<span>…</span></div>}
      </div>
      <form className="message-form" onSubmit={submit}>
        <label className="visually-hidden" htmlFor="intake-message">Message</label>
        <textarea
          id="intake-message"
          aria-label="Message"
          placeholder="Describe the challenge or opportunity…"
          rows={2}
          maxLength={20000}
          value={text}
          disabled={disabled || busy}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <button type="submit" className="send-button" aria-label="Send" disabled={disabled || busy || !text.trim()} title="Send message">
          <span aria-hidden="true">↑</span>
        </button>
        <span className="input-hint">Enter to send | Shift + Enter for a new line</span>
      </form>
    </div>
  );
}