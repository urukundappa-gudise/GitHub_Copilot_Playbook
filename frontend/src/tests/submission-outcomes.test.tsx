import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it.each(['throwing', 'unavailable'] as const)('retains the confirmed summary when modality is %s', async (failure) => {
    if (failure === 'throwing') {
      vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(() => { throw new Error('unavailable'); });
    } else {
      vi.spyOn(HTMLDialogElement.prototype, 'showModal');
      Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { value: undefined, configurable: true });
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'submitted', submitted_at: '2026-11-11T12:00:00Z' }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /submit idea/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/idea is submitted.*dialog could not be displayed/i);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start a new idea/i })).toBeEnabled();
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it('coalesces repeated Submit while readiness is pending and recovers a confirmed receipt without resubmitting', async () => {
    let finishReadiness: (value: Response) => void = () => { throw new Error('Readiness was not requested'); };
    const pending = new Promise<Response>((resolve) => { finishReadiness = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockReturnValueOnce(pending)
      .mockRejectedValueOnce(new TypeError('response lost'))
      .mockResolvedValueOnce(response({ ...state(sessionId), status: 'submitted', submitted_at: '2026-11-11T12:00:00Z' }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    const submit = await screen.findByRole('button', { name: /submit idea/i });
    fireEvent.click(submit);
    fireEvent.click(submit);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    await act(async () => { finishReadiness(response(state(sessionId))); });
    fireEvent.click(await screen.findByRole('button', { name: /check submission status/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/submit'))).toHaveLength(1);
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeDisabled();
  });

  it('preserves invalid-email readiness feedback without dispatching Submit', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockResolvedValueOnce(response({ ...state(sessionId, false), readiness: { ready: false, missing_fields: [], invalid_fields: ['submitter_email'] } }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /submit idea/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('submitter_email');
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeEnabled();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('gates active uploads and ignores their completion after unmount and a new mount', async () => {
    let finishUpload: (value: Response) => void = () => { throw new Error('Upload was not requested'); };
    const pending = new Promise<Response>((resolve) => { finishUpload = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }))
      .mockResolvedValueOnce(response(state(sessionId)))
      .mockReturnValueOnce(pending)
      .mockResolvedValueOnce(response({ session_id: 'fresh-mount', status: 'in_progress', schema_version: 'active' }))
      .mockResolvedValueOnce(response(state('fresh-mount')));
    vi.stubGlobal('fetch', fetchMock);
    const old = render(<App />);
    const picker = await screen.findByLabelText('Choose a document or audio file');
    await waitFor(() => expect(picker).toBeEnabled());
    fireEvent.change(picker, { target: { files: [new File(['safe'], 'safe.pdf', { type: 'application/pdf' })] } });
    expect(screen.getByRole('button', { name: /submit idea/i })).toBeDisabled();
    old.unmount();
    render(<App />);
    await waitFor(() => expect(screen.getByRole('button', { name: /submit idea/i })).toBeEnabled());
    await act(async () => { finishUpload(response({
      request_id: 'obsolete', field_updates: [], clarification: null, status: 'in_progress',
      safety_notice: { code: 'NO_FACTS_REJECTED', status: 'denied', reason: 'NoFacts', reasons: ['number'] },
    })); });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /submit idea/i })).toBeEnabled();
  });

  it('keeps Submit gated until every declaration save settles after an early failure', async () => {
    let finishSignature: (value: Response) => void = () => { throw new Error('No signature save'); };
    let finishDate: (value: Response) => void = () => { throw new Error('No date save'); };
    const signature = new Promise<Response>((resolve) => { finishSignature = resolve; });
    const date = new Promise<Response>((resolve) => { finishDate = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }))
      .mockResolvedValueOnce(response({ ...state(sessionId), sections: [{ section_key: 'section_06', fields: [
        { field_key: 'declaration_accepted', mandatory: true, human_only: true, value: 'true', origin: 'human_entered' },
        { field_key: 'submitter_signature', mandatory: true, human_only: true, value: 'Test signature', origin: 'human_entered' },
        { field_key: 'date_of_submission', mandatory: true, human_only: true, value: '2026-11-11', origin: 'human_entered' },
      ] }] }))
      .mockResolvedValueOnce(response({ error: { code: 'SERVICE_UNAVAILABLE' } }, 503))
      .mockReturnValueOnce(signature)
      .mockReturnValueOnce(date);
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Save Declaration' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    const submit = screen.getByRole('button', { name: /submit idea/i });
    expect(submit).toBeDisabled();
    await act(async () => { finishSignature(response({ field_key: 'submitter_signature', value: 'Test signature', origin: 'human_entered' })); });
    expect(submit).toBeDisabled();
    await act(async () => { finishDate(response({ field_key: 'date_of_submission', value: '2026-11-11', origin: 'human_entered' })); });
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be fully saved/i);
    await waitFor(() => expect(submit).toBeEnabled());
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

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