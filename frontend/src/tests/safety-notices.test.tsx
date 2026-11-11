import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { connectIntakeSocket, getFieldState, submitSession } from '../services/intake';

const sessionId = 'session-notices';

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function initialState() {
  return {
    session_id: sessionId,
    schema_version: 'active',
    sections: [],
    status: 'in_progress',
    submitted_at: null,
    readiness: { ready: false, missing_fields: [], invalid_fields: [] },
  };
}

describe('safety notices', () => {
  const denial = {
    code: 'NO_FACTS_REJECTED', status: 'denied', reason: 'NoFacts', reasons: ['number'],
  };
  const safeUpdates = [{ field_key: 'problem_statement', value: 'A safe correction.', origin: 'ai_extracted' }];

  it('links only the next dispatched operation after selection replacement despite concurrent uploads', async () => {
    let finishUnlinked: (value: Response) => void = () => { throw new Error('No upload'); };
    let finishLinked: (value: Response) => void = () => { throw new Error('No correction'); };
    const unlinked = new Promise<Response>((resolve) => { finishUnlinked = resolve; });
    const linked = new Promise<Response>((resolve) => { finishLinked = resolve; });
    const safe = { request_id: 'accepted', field_updates: safeUpdates, clarification: null, status: 'in_progress', safety_notice: null };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }))
      .mockResolvedValueOnce(response(initialState()))
      .mockResolvedValueOnce(response({ request_id: 'first', field_updates: [], clarification: null, status: 'in_progress', safety_notice: denial }))
      .mockResolvedValueOnce(response({ request_id: 'second', field_updates: [], clarification: null, status: 'in_progress', safety_notice: { ...denial, reasons: ['cost'] } }))
      .mockReturnValueOnce(unlinked)
      .mockReturnValueOnce(linked)
      .mockImplementation(() => Promise.resolve(response(safe)));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    const composer = await screen.findByRole('textbox', { name: 'Message' });
    const send = screen.getByRole('button', { name: 'Send' });
    for (const text of ['First request', 'Second request']) {
      await waitFor(() => expect(composer).toBeEnabled());
      fireEvent.change(composer, { target: { value: text } });
      fireEvent.click(send);
      await waitFor(() => expect(composer).toBeEnabled());
    }
    const banners = await screen.findAllByRole('alert');
    expect(banners).toHaveLength(2);
    const picker = screen.getByLabelText('Choose a document or audio file');
    const file = new File(['safe'], 'safe.pdf', { type: 'application/pdf' });
    fireEvent.change(picker, { target: { files: [file] } });
    fireEvent.click(within(banners[0]).getByRole('button', { name: 'Correct this input' }));
    fireEvent.click(within(banners[1]).getByRole('button', { name: 'Correct this input' }));
    expect(screen.getByText(/correcting the selected.*cost/i)).toBeInTheDocument();
    fireEvent.change(composer, { target: { value: 'Selected correction' } });
    fireEvent.click(send);
    await act(async () => { finishUnlinked(response(safe)); });
    expect(screen.getAllByRole('alert')).toHaveLength(2);
    fireEvent.change(picker, { target: { files: [file] } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(7));
    expect(screen.getAllByRole('alert')).toHaveLength(2);
    await act(async () => { finishLinked(response({ ...safe, request_id: 'linked-correction' })); });
    expect(screen.getAllByRole('alert')).toHaveLength(1);
    expect(screen.getByRole('alert')).toHaveTextContent(/unverified numbers/i);
    fireEvent.click(screen.getByRole('button', { name: 'Correct this input' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel correction' }));
    fireEvent.change(picker, { target: { files: [file] } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(8));
    expect(screen.getByRole('alert')).toHaveTextContent(/unverified numbers/i);
  });

  it.each(['upload', 'protected', 'empty', 'legacy', 'mixed', 'failed', 'invalid'] as const)(
    'keeps correction ownership explicit for %s results',
    async (outcome) => {
      const correction = {
        request_id: 'correction', field_updates: outcome === 'empty' ? [] : outcome === 'protected'
          ? [{ field_key: 'submitter_signature', value: 'Not human', origin: 'ai_extracted' }] : safeUpdates,
        clarification: null, status: 'in_progress',
        ...(outcome === 'legacy' ? {} : { safety_notice: outcome === 'mixed' ? denial : null }),
      };
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
        .mockResolvedValueOnce(response(initialState()))
        .mockResolvedValueOnce(response({
          request_id: 'original', field_updates: [], clarification: null, status: 'in_progress', safety_notice: denial,
        }))
        .mockResolvedValueOnce(outcome === 'failed' || outcome === 'invalid'
          ? response({ error: { code: 'SERVICE_UNAVAILABLE' } }, outcome === 'failed' ? 503 : 422)
          : response(correction));
      vi.stubGlobal('fetch', fetchMock);
      render(<App />);
      const composer = await screen.findByRole('textbox', { name: /message/i });
      fireEvent.change(composer, { target: { value: 'Rejected request' } });
      fireEvent.click(screen.getByRole('button', { name: 'Send' }));
      const original = await screen.findByText(/unverified numbers/i);
      fireEvent.click(screen.getByRole('button', { name: /correct this input/i }));
      const picker = screen.getByLabelText('Choose a document or audio file');
      fireEvent.change(picker, { target: { files: [] } });
      expect(screen.getByText(/correcting the selected/i)).toBeInTheDocument();
      expect(fetchMock).toHaveBeenCalledTimes(3);
      if (outcome === 'upload' || outcome === 'protected') {
        fireEvent.change(picker, { target: { files: [new File(['safe'], 'safe.pdf', { type: 'application/pdf' })] } });
      } else {
        fireEvent.change(composer, { target: { value: 'Correction' } });
        fireEvent.click(screen.getByRole('button', { name: 'Send' }));
      }
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
      await waitFor(() => expect(composer).toBeEnabled());
      if (outcome === 'upload') {
        await waitFor(() => expect(original).not.toBeInTheDocument());
        expect(String(fetchMock.mock.calls[3][0])).toContain('/sources/pdf');
      } else {
        expect(original).toBeInTheDocument();
        if (outcome === 'mixed') expect(screen.getAllByText(/unverified numbers/i)).toHaveLength(2);
      }
      expect(screen.queryByText(/correcting the selected/i)).not.toBeInTheDocument();
    },
  );

  it.each(['dismissed', 'corrected'] as const)('does not resurrect a %s request on replay', async (resolution) => {
    const rejected = {
      request_id: 'replayed', field_updates: [], clarification: null, status: 'in_progress', safety_notice: denial,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(initialState()))
      .mockResolvedValueOnce(response(rejected))
      .mockResolvedValueOnce(response({ request_id: 'safe', field_updates: safeUpdates, clarification: null, status: 'in_progress', safety_notice: null }))
      .mockResolvedValueOnce(response(rejected));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    const composer = await screen.findByRole('textbox', { name: /message/i });
    const send = screen.getByRole('button', { name: 'Send' });
    fireEvent.change(composer, { target: { value: 'Original request' } });
    fireEvent.click(send);
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: resolution === 'dismissed' ? 'Dismiss' : 'Correct this input' }));
    fireEvent.change(composer, { target: { value: 'Accepted update' } });
    fireEvent.click(send);
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    await waitFor(() => expect(composer).toBeEnabled());
    fireEvent.change(composer, { target: { value: 'Replay request' } });
    fireEvent.click(send);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    await waitFor(() => expect(composer).toBeEnabled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('cleans request resources immediately when socket send throws', async () => {
    vi.useFakeTimers();
    class BrokenSocket extends EventTarget {
      static current: BrokenSocket;
      constructor() { super(); BrokenSocket.current = this; }
      send() { throw new Error('send failed'); }
      close() { this.dispatchEvent(new Event('close')); }
    }
    vi.stubGlobal('WebSocket', BrokenSocket);
    const connecting = connectIntakeSocket(sessionId);
    BrokenSocket.current.dispatchEvent(new Event('open'));
    const connection = await connecting;
    if (!connection) throw new Error('No connection');
    const remove = vi.spyOn(BrokenSocket.current, 'removeEventListener');
    await expect(connection.sendMessage('Safe text', 'request')).rejects.toThrow();
    expect(vi.getTimerCount()).toBe(0);
    expect(remove).toHaveBeenCalledWith('message', expect.any(Function));
    expect(remove).toHaveBeenCalledWith('close', expect.any(Function));
    connection.close();
    vi.useRealTimers();
  });

  it.each([null, 'not-a-timestamp'])('rejects invalid submitted state timestamps: %s', async (timestamp) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      ...initialState(), status: 'submitted', submitted_at: timestamp,
    })));
    await expect(getFieldState(sessionId)).rejects.toThrow(/invalid response/i);
  });

  it('rejects receipts for another session', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      session_id: 'another-session', status: 'submitted', submitted_at: '2026-11-11T12:00:00Z',
    })));
    await expect(submitSession(sessionId)).rejects.toThrow(/invalid response/i);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.useRealTimers();
  });

  it('renders category-only partial denial without blocking editing or stealing focus', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(initialState()))
      .mockResolvedValueOnce(response({
        request_id: 'logical-request-1',
        field_updates: [{ field_key: 'problem_statement', value: 'Policy discovery is difficult.', origin: 'ai_extracted' }],
        clarification: null,
        status: 'in_progress',
        safety_notice: {
          code: 'NO_FACTS_REJECTED',
          status: 'denied',
          reason: 'NoFacts',
          reasons: ['number', 'percentage'],
        },
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    const composer = await screen.findByRole('textbox', { name: /message/i });
    composer.focus();
    fireEvent.change(composer, { target: { value: 'A safe clarification.' } });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));

    const banner = await screen.findByRole('alert');
    expect(banner).toHaveTextContent(/some information was not accepted/i);
    expect(banner).toHaveTextContent(/unverified numbers/i);
    expect(banner).toHaveTextContent(/unverified percentages/i);
    expect(banner).not.toHaveTextContent(/private rejected claim/i);
    expect(await screen.findByText('Policy discovery is difficult.')).toBeInTheDocument();
    await waitFor(() => expect(composer).toBeEnabled());
    expect(document.activeElement).not.toBe(banner);

    fireEvent.click(screen.getByRole('button', { name: /correct this input/i }));
    expect(await screen.findByText(/correcting the selected rejected input: number, percentage/i)).toBeInTheDocument();
    expect(document.activeElement).toBe(composer);
    fireEvent.click(screen.getByRole('button', { name: /cancel correction/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /correct this input/i })).toHaveFocus());
  });

  it('dismisses the inline denial without resetting the conversation', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(initialState()))
      .mockResolvedValueOnce(response({
        request_id: 'logical-request-2',
        field_updates: [],
        clarification: null,
        status: 'in_progress',
        safety_notice: { code: 'NO_FACTS_REJECTED', status: 'denied', reason: 'NoFacts', reasons: [] },
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole('textbox', { name: /message/i }), {
      target: { value: 'A qualitative request.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByRole('textbox', { name: /message/i })).toBeEnabled();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/sessions/')).length).toBe(2);
  });

  it('decodes the terminal WebSocket notice and preserves the caller request ID', async () => {
    class MockSocket extends EventTarget {
      static active: MockSocket;
      sent: string[] = [];

      constructor() {
        super();
        MockSocket.active = this;
      }

      send(data: string) {
        this.sent.push(data);
      }

      close() {
        this.dispatchEvent(new Event('close'));
      }
    }
    vi.stubGlobal('WebSocket', MockSocket);
    const connectionPromise = connectIntakeSocket(sessionId);
    MockSocket.active.dispatchEvent(new Event('open'));
    const connection = await connectionPromise;
    expect(connection).not.toBeNull();
    if (!connection) throw new Error('Socket setup failed.');

    const resultPromise = connection.sendMessage('Transient request.', 'stable-request-id');
    expect(JSON.parse(MockSocket.active.sent[0])).toMatchObject({
      request_id: 'stable-request-id',
      type: 'client.message',
    });
    MockSocket.active.dispatchEvent(new MessageEvent('message', {
      data: JSON.stringify({
        type: 'server.submission.status',
        request_id: 'stable-request-id',
        payload: {
          status: 'in_progress',
          safety_notice: {
            code: 'NO_FACTS_REJECTED',
            status: 'denied',
            reason: 'NoFacts',
            reasons: ['word_quantity'],
          },
        },
      }),
    }));

    await expect(resultPromise).resolves.toMatchObject({
      request_id: 'stable-request-id',
      status: 'in_progress',
      safety_notice: { status: 'denied', reason: 'NoFacts', reasons: ['word_quantity'] },
    });
    connection.close();
  });

  it('handles Escape only inside the banner and restores the initiating composer', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(initialState()))
      .mockResolvedValueOnce(response({
        request_id: 'logical-request-escape',
        field_updates: [],
        clarification: null,
        status: 'in_progress',
        safety_notice: { code: 'NO_FACTS_REJECTED', status: 'denied', reason: 'NoFacts', reasons: ['number'] },
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    const composer = await screen.findByRole('textbox', { name: /message/i });
    composer.focus();
    fireEvent.change(composer, { target: { value: 'A qualitative request.' } });
    const form = composer.closest('form');
    if (!form) throw new Error('Message form was not rendered.');
    fireEvent.submit(form);
    const banner = await screen.findByRole('alert');

    const submit = screen.getByRole('button', { name: /submit/i });
    submit.focus();
    fireEvent.keyDown(submit, { key: 'Escape' });
    expect(screen.getByRole('alert')).toBeInTheDocument();

    screen.getByRole('button', { name: /dismiss/i }).focus();
    fireEvent.keyDown(screen.getByRole('button', { name: /dismiss/i }), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    await waitFor(() => expect(composer).toHaveFocus());
    expect(banner).toHaveAttribute('role', 'alert');
    expect(banner).not.toHaveAttribute('aria-modal');
  });

  it('reuses one request ID when a WebSocket operation falls back to HTTP', async () => {
    class MockSocket extends EventTarget {
      static active: MockSocket;
      sent: string[] = [];

      constructor() {
        super();
        MockSocket.active = this;
        queueMicrotask(() => this.dispatchEvent(new Event('open')));
      }

      send(data: string) {
        this.sent.push(data);
      }

      close() {
        this.dispatchEvent(new Event('close'));
      }
    }
    vi.stubEnv('MODE', 'development');
    vi.stubGlobal('WebSocket', MockSocket);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(initialState()))
      .mockResolvedValueOnce(response({
        request_id: 'logical-fallback-id',
        field_updates: safeUpdates,
        clarification: null,
        status: 'in_progress',
        safety_notice: null,
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole('textbox', { name: /message/i }), {
      target: { value: 'A qualitative request.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));
    await waitFor(() => expect(MockSocket.active.sent).toHaveLength(1));
    const firstRequest = JSON.parse(MockSocket.active.sent[0]) as { request_id: string };
    MockSocket.active.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({
      type: 'server.submission.status', request_id: firstRequest.request_id,
      payload: { status: 'in_progress', safety_notice: denial },
    }) }));
    await screen.findByRole('alert');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: 'Correct this input' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Message' }), { target: { value: 'Linked correction' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(MockSocket.active.sent).toHaveLength(2));
    const websocketRequest = JSON.parse(MockSocket.active.sent[1]) as { request_id: string };
    MockSocket.active.close();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const httpRequest = JSON.parse(String(fetchMock.mock.calls[2][1]?.body)) as { request_id: string };
    expect(httpRequest.request_id).toBe(websocketRequest.request_id);
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });

  it('rejects malformed notice metadata as a protocol error without transport retry', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(initialState()))
      .mockResolvedValueOnce(response({
        request_id: 'malformed-notice-id',
        field_updates: [],
        clarification: null,
        status: 'in_progress',
        safety_notice: { code: 'UNRECOGNIZED', status: 'denied', reason: 'NoFacts', reasons: ['number'] },
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole('textbox', { name: /message/i }), {
      target: { value: 'A qualitative request.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));

    expect(await screen.findByText(/could not process that turn/i)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('clears only the explicitly selected banner after accepted correction updates', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(initialState()))
      .mockResolvedValueOnce(response({
        request_id: 'rejection-one', field_updates: [], clarification: null, status: 'in_progress',
        safety_notice: { code: 'NO_FACTS_REJECTED', status: 'denied', reason: 'NoFacts', reasons: ['number'] },
      }))
      .mockResolvedValueOnce(response({
        request_id: 'rejection-two', field_updates: [], clarification: null, status: 'in_progress',
        safety_notice: { code: 'NO_FACTS_REJECTED', status: 'denied', reason: 'NoFacts', reasons: ['cost'] },
      }))
      .mockResolvedValueOnce(response({
        request_id: 'correction-result',
        field_updates: [{ field_key: 'problem_statement', value: 'A safe correction.', origin: 'ai_extracted' }],
        clarification: null,
        status: 'in_progress',
        safety_notice: null,
      }))
      .mockResolvedValueOnce(response({
        request_id: 'unlinked-result',
        field_updates: [{ field_key: 'idea_title', value: 'Another safe update.', origin: 'ai_extracted' }],
        clarification: null,
        status: 'in_progress',
        safety_notice: null,
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    const composer = await screen.findByRole('textbox', { name: /message/i });
    const send = screen.getByRole('button', { name: /send/i });
    fireEvent.change(composer, { target: { value: 'First rejected request.' } });
    fireEvent.click(send);
    await screen.findByText(/unverified numbers/i);
    fireEvent.change(composer, { target: { value: 'Second rejected request.' } });
    fireEvent.click(send);
    await screen.findByText(/unverified costs/i);

    const banners = screen.getAllByRole('alert');
    expect(banners).toHaveLength(2);
    fireEvent.click(within(banners[0]).getByRole('button', { name: /correct this input/i }));
    fireEvent.change(composer, { target: { value: 'A safe correction.' } });
    fireEvent.click(send);

    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(1));
    expect(screen.getByRole('alert')).toHaveTextContent(/unverified costs/i);
    fireEvent.change(composer, { target: { value: 'Unlinked safe update.' } });
    fireEvent.click(send);

    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(1));
    expect(screen.getByRole('alert')).toHaveTextContent(/unverified costs/i);
  });
});