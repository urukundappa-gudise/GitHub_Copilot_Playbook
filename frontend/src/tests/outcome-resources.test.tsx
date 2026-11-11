import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { OutcomeDialog } from '../components/OutcomeDialog';
import { SafetyDenialBanner } from '../components/SafetyDenialBanner';
import { connectIntakeSocket } from '../services/intake';

function response(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } });
}

describe('owned outcome resources', () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

  it('releases 100 feedback and successful/failed transport cycles without retained resources', async () => {
    vi.useFakeTimers();
    const writes = vi.spyOn(Storage.prototype, 'setItem');
    const deletes = vi.spyOn(Storage.prototype, 'removeItem');
    const clears = vi.spyOn(Storage.prototype, 'clear');
    const unhandled = vi.fn();
    window.addEventListener('unhandledrejection', unhandled);
    class TrackedSocket extends EventTarget {
      static current: TrackedSocket;
      listeners = new Map<string, Set<EventListenerOrEventListenerObject>>();
      closed = false;
      constructor() { super(); TrackedSocket.current = this; }
      override addEventListener(type: string, callback: EventListenerOrEventListenerObject | null, options?: AddEventListenerOptions | boolean) {
        if (callback) {
          const callbacks = this.listeners.get(type) ?? new Set<EventListenerOrEventListenerObject>();
          callbacks.add(callback);
          this.listeners.set(type, callbacks);
        }
        super.addEventListener(type, callback, options);
      }
      override removeEventListener(type: string, callback: EventListenerOrEventListenerObject | null, options?: EventListenerOptions | boolean) {
        if (callback) this.listeners.get(type)?.delete(callback);
        super.removeEventListener(type, callback, options);
      }
      send() {}
      close() { this.closed = true; this.dispatchEvent(new Event('close')); }
    }
    vi.stubGlobal('WebSocket', TrackedSocket);
    const baseline = document.querySelectorAll('dialog, [data-notice-key]').length;
    for (let cycle = 0; cycle < 100; cycle++) {
      const timerBaseline = vi.getTimerCount();
      const connecting = connectIntakeSocket('resource-session');
      const socket = TrackedSocket.current;
      if (cycle % 10 === 0) {
        socket.dispatchEvent(new Event('error'));
        expect(await connecting).toBeNull();
      } else {
        socket.dispatchEvent(new Event('open'));
        const connection = await connecting;
        if (!connection) throw new Error('Connection setup failed');
        const outcome = cycle % 7;
        if (outcome === 6) vi.spyOn(socket, 'send').mockImplementation(() => { throw new Error('send failed'); });
        const pending = connection.sendMessage('Qualitative request', 'resource-request');
        const checked = outcome === 0
          ? expect(pending).resolves.toMatchObject({ status: 'in_progress' })
          : expect(pending).rejects.toThrow();
        if (outcome === 0) {
          socket.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({
            type: 'server.submission.status', request_id: 'resource-request',
            payload: { status: 'in_progress', safety_notice: null },
          }) }));
        } else if (outcome === 1) socket.dispatchEvent(new Event('error'));
        else if (outcome === 2) socket.close();
        else if (outcome === 3) socket.dispatchEvent(new MessageEvent('message', { data: 'malformed' }));
        else if (outcome === 4) await vi.advanceTimersByTimeAsync(15000);
        else if (outcome === 5) socket.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({
          type: 'server.error', request_id: 'resource-request', payload: { code: 'SOURCE_INVALID' },
        }) }));
        await checked;
        connection.close();
      }
      expect(socket.closed).toBe(true);
      expect([...socket.listeners.values()].reduce((count, callbacks) => count + callbacks.size, 0)).toBe(0);
      expect(vi.getTimerCount()).toBe(timerBaseline);
      const view = render(<>
        <OutcomeDialog open onDismiss={vi.fn()} onStartNew={vi.fn()} />
        <SafetyDenialBanner noticeKey={`notice-${cycle}`}
          notice={{ code: 'NO_FACTS_REJECTED', status: 'denied', reason: 'NoFacts', reasons: ['number'] }}
          onDismiss={vi.fn()} onCorrect={vi.fn()} />
      </>);
      fireEvent.click(screen.getByRole('button', { name: 'Close' }));
      fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
      view.unmount();
      expect(document.querySelectorAll('dialog, [data-notice-key]')).toHaveLength(baseline);
      await vi.runOnlyPendingTimersAsync();
      expect(vi.getTimerCount()).toBe(0);
    }
    expect(writes).not.toHaveBeenCalled();
    expect(deletes).not.toHaveBeenCalled();
    expect(clears).not.toHaveBeenCalled();
    expect(unhandled).not.toHaveBeenCalled();
    window.removeEventListener('unhandledrejection', unhandled);
  }, 20000);

  it('clears ten populated intakes and cancels owned focus work on teardown', async () => {
    const frames = new Set<number>();
    const requestFrame = window.requestAnimationFrame.bind(window);
    const cancelFrame = window.cancelAnimationFrame.bind(window);
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      const frame = requestFrame((time) => { frames.delete(frame); callback(time); });
      frames.add(frame);
      return frame;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((frame) => {
      frames.delete(frame);
      cancelFrame(frame);
    });
    const writes = vi.spyOn(Storage.prototype, 'setItem');
    const deletes = vi.spyOn(Storage.prototype, 'removeItem');
    const clears = vi.spyOn(Storage.prototype, 'clear');
    let sessionNumber = 0;
    const serialize = vi.spyOn(JSON, 'stringify');
    const unhandled = vi.fn();
    window.addEventListener('unhandledrejection', unhandled);
    const submitted = new Set<string>();
    const failedPreparation = new Set<string>();
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/v1/sessions') {
        return Promise.resolve(response({ session_id: `cycle-${++sessionNumber}`, status: 'in_progress', schema_version: 'active' }));
      }
      const session = url.split('/')[4];
      if (init?.method === 'PUT') {
        const body: unknown = JSON.parse(String(init.body));
        if (typeof body !== 'object' || body === null || !('value' in body)) throw new Error('Invalid save fixture');
        return Promise.resolve(response({
          field_key: url.slice(url.lastIndexOf('/') + 1), value: String(body.value), origin: 'human_entered',
        }));
      }
      if (url.endsWith('/submit')) {
        submitted.add(session);
        return Promise.resolve(response({ session_id: session, status: 'submitted', submitted_at: '2026-11-11T12:00:00Z' }));
      }
      if (url.endsWith('/messages') || url.includes('/sources/')) {
        return Promise.resolve(response({
          request_id: url.includes('/sources/') ? `upload-${session}` : JSON.parse(String(init?.body)).request_id,
          field_updates: [{ field_key: 'problem_statement', value: 'Captured safe detail', origin: 'ai_extracted' }],
          clarification: { field_key: 'idea_title', question: 'What is the title?' },
          safety_notice: { code: 'NO_FACTS_REJECTED', status: 'denied', reason: 'NoFacts', reasons: ['number'] },
          status: 'in_progress',
        }));
      }
      if (sessionNumber > 1 && !failedPreparation.has(session)) {
        failedPreparation.add(session);
        return Promise.resolve(new Response(JSON.stringify({ error: { code: 'SERVICE_UNAVAILABLE' } }), {
          status: 503, headers: { 'content-type': 'application/json' },
        }));
      }
      return Promise.resolve(response({
        session_id: session, schema_version: 'active', status: 'in_progress', submitted_at: null,
        sections: [{ section_key: 'section_01', fields: [
          { field_key: 'problem_statement', mandatory: true, human_only: false },
          { field_key: 'submitter_signature', mandatory: true, human_only: true },
          { field_key: 'date_of_submission', mandatory: true, human_only: true },
          { field_key: 'declaration_accepted', mandatory: true, human_only: true },
          { field_key: 'reviewer_notes', mandatory: false, human_only: true },
        ] }],
        readiness: { ready: true, missing_fields: [], invalid_fields: [] },
      }));
    }));
    const view = render(<App />);
    for (let cycle = 0; cycle < 10; cycle++) {
      const composer = await screen.findByRole('textbox', { name: 'Message' });
      await waitFor(() => expect(composer).toBeEnabled());
      fireEvent.change(composer, { target: { value: 'Old draft conversation' } });
      fireEvent.click(screen.getByRole('button', { name: 'Send' }));
      await screen.findByText('What is the title?');
      fireEvent.click(screen.getByRole('checkbox'));
      fireEvent.change(screen.getByLabelText('Submitter Signature'), { target: { value: 'Saved signature' } });
      fireEvent.change(screen.getByLabelText('Date of Submission'), { target: { value: '2026-11-11' } });
      fireEvent.click(screen.getByRole('button', { name: 'Save Declaration' }));
      await waitFor(() => expect(screen.getByRole('button', { name: 'Save Declaration' })).toBeEnabled());
      fireEvent.change(screen.getByLabelText('Additional Notes for Reviewer'), { target: { value: 'Saved reviewer note' } });
      fireEvent.click(screen.getByRole('button', { name: 'Save Reviewer Notes' }));
      await waitFor(() => expect(screen.getByRole('button', { name: 'Save Reviewer Notes' })).toBeEnabled());
      fireEvent.change(screen.getByLabelText('Choose a document or audio file'), {
        target: { files: [new File(['safe'], 'safe.pdf', { type: 'application/pdf' })] },
      });
      await waitFor(() => expect(screen.getByRole('button', { name: /submit idea/i })).toBeEnabled());
      fireEvent.click(screen.getByRole('button', { name: /submit idea/i }));
      await screen.findByRole('dialog');
      if (cycle % 2 === 0) fireEvent.click(screen.getByRole('button', { name: 'Close' }));
      fireEvent.click(screen.getByRole('button', { name: 'Start a new idea' }));
      const retry = await screen.findByRole('button', { name: 'Retry new idea setup' });
      expect(screen.getByLabelText('Submitter Signature')).toHaveValue('Saved signature');
      expect(screen.getByRole('textbox', { name: 'Message' })).toBeDisabled();
      fireEvent.click(retry);
      await waitFor(() => expect(screen.queryByText('Old draft conversation')).not.toBeInTheDocument());
      expect(screen.queryByText('What is the title?')).not.toBeInTheDocument();
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.getByRole('textbox', { name: 'Message' })).toHaveValue('');
      expect(screen.getByLabelText('Submitter Signature')).toHaveValue('');
      expect(screen.getByLabelText('Date of Submission')).toHaveValue('');
      expect(screen.getByRole('checkbox')).not.toBeChecked();
      expect(screen.getByLabelText('Additional Notes for Reviewer')).toHaveValue('');
      expect(screen.getByText('0%')).toBeInTheDocument();
      expect(screen.getByLabelText('Choose a document or audio file')).toHaveValue('');
    }
    expect(submitted.size).toBe(10);
    expect(sessionNumber).toBe(11);
    expect(failedPreparation.size).toBe(10);
    view.unmount();
    expect(frames.size).toBe(0);
    serialize.mockClear();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    expect(serialize).not.toHaveBeenCalled();
    expect(unhandled).not.toHaveBeenCalled();
    window.removeEventListener('unhandledrejection', unhandled);
    expect(document.querySelectorAll('dialog, [data-notice-key]')).toHaveLength(0);
    expect(writes).not.toHaveBeenCalled();
    expect(deletes).not.toHaveBeenCalled();
    expect(clears).not.toHaveBeenCalled();
  }, 20000);
});
