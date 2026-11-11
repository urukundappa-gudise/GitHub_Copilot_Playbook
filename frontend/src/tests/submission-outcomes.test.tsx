import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

const sessionId = 'session-submission';

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function state(session: string, ready = true) {
  return {
    session_id: session,
    schema_version: 'active',
    sections: [],
    status: 'in_progress',
    submitted_at: null,
    readiness: { ready, missing_fields: [], invalid_fields: [] },
  };
}

describe('submission outcomes', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('does not submit until the employee selects Submit', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({
        session_id: sessionId,
        status: 'in_progress',
        schema_version: 'active',
      }, 201))
      .mockResolvedValueOnce(response(state(sessionId)));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    await screen.findByRole('textbox', { name: /message/i });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('/submit'), expect.anything());
  });

  it('blocks submission while declaration edits are unsaved', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response({
        ...state(sessionId),
        sections: [{
          section_key: 'section_06',
          fields: [
            { field_key: 'declaration_accepted', mandatory: true, human_only: true, value: 'true', origin: 'human_entered' },
            { field_key: 'submitter_signature', mandatory: true, human_only: true, value: 'Jordan Lee', origin: 'human_entered' },
            { field_key: 'date_of_submission', mandatory: true, human_only: true, value: '2026-11-11', origin: 'human_entered' },
          ],
        }],
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole('textbox', { name: /submitter signature/i }), {
      target: { value: 'Changed signature' },
    });
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/save your declaration/i);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/submit'))).toHaveLength(0);
  });

  it('disables Submit while an input operation is active', async () => {
    let finishMessage: ((value: Response) => void) | undefined;
    const pendingMessage = new Promise<Response>((resolve) => {
      finishMessage = resolve;
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockReturnValueOnce(pendingMessage);
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole('textbox', { name: /message/i }), {
      target: { value: 'A qualitative request.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));
    await screen.findByText(/reviewing your message/i);

    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/submit'))).toHaveLength(0);
    finishMessage?.(response({
      request_id: 'active-message-result',
      field_updates: [],
      clarification: null,
      status: 'in_progress',
      safety_notice: null,
    }));
    await waitFor(() => expect(screen.getByRole('button', { name: /submit/i })).toBeEnabled());
  });

  it('shows one confirmation and keeps the submitted idea frozen after Escape', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response({
        session_id: sessionId,
        status: 'submitted',
        submitted_at: '2026-11-11T12:00:00Z',
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /submit/i }));
    expect(await screen.findByRole('dialog')).toHaveAccessibleName(/idea submitted/i);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole('button', { name: /start a new idea/i })).toHaveFocus());
    expect(screen.getByRole('textbox', { name: /message/i })).toBeDisabled();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/submit'))).toHaveLength(1);
  });

  it('starts fresh only after explicit acknowledgment', async () => {
    const nextSessionId = 'session-fresh';
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'submitted', submitted_at: '2026-11-11T12:00:00Z' }))
      .mockResolvedValueOnce(response({ session_id: nextSessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(state(nextSessionId)));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /submit/i }));
    fireEvent.click(await screen.findByRole('button', { name: /start a new idea/i }));

    await waitFor(() => expect(fetchMock.mock.calls.filter(([url, init]) => String(url) === '/api/v1/sessions' && init?.method === 'POST')).toHaveLength(2));
    expect(screen.getByRole('textbox', { name: /message/i })).toBeEnabled();
    await waitFor(() => expect(screen.getByRole('textbox', { name: /message/i })).toHaveFocus());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps an unknown result frozen until the same session is read authoritatively', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockRejectedValueOnce(new TypeError('network unavailable'))
      .mockResolvedValueOnce(response(state(sessionId)));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /submit/i }));
    expect(await screen.findByRole('button', { name: /check submission status/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /message/i })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /check submission status/i }));

    expect(await screen.findByText(/still in progress/i)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /message/i })).toBeEnabled();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/submit'))).toHaveLength(1);
  });

  it('reuses the allocated next session when fresh setup fails', async () => {
    const nextSessionId = 'session-fresh-retry';
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'submitted', submitted_at: '2026-11-11T12:00:00Z' }))
      .mockResolvedValueOnce(response({ session_id: nextSessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response({ error: { code: 'SERVICE_UNAVAILABLE' } }, 503))
      .mockResolvedValueOnce(response(state(nextSessionId)));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /submit/i }));
    fireEvent.click(await screen.findByRole('button', { name: /start a new idea/i }));
    fireEvent.click(await screen.findByRole('button', { name: /retry new idea setup/i }));

    await waitFor(() => expect(screen.getByRole('textbox', { name: /message/i })).toBeEnabled());
    const createCalls = fetchMock.mock.calls.filter(([url, init]) => String(url) === '/api/v1/sessions' && init?.method === 'POST');
    expect(createCalls).toHaveLength(2);
    expect(String(fetchMock.mock.calls[6][0])).toContain(encodeURIComponent(nextSessionId));
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/submit'))).toHaveLength(1);
  });
});