import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

const sessionId = 'session-test';

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('intake flow', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('creates a session, submits chat, and renders safe field updates', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response({
        session_id: sessionId,
        schema_version: 'active',
        sections: [],
        status: 'in_progress',
        submitted_at: null,
        readiness: { ready: false, missing_fields: [], invalid_fields: [] },
      }))
      .mockResolvedValueOnce(response({
        request_id: 'request-1',
        field_updates: [{ field_key: 'problem_statement', value: 'Policy discovery is difficult.', origin: 'ai_extracted' }],
        clarification: { field_key: 'idea_title', question: 'What is the title of your idea?' },
        status: 'in_progress',
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    await screen.findByRole('textbox', { name: /message/i });
    fireEvent.change(screen.getByRole('textbox', { name: /message/i }), {
      target: { value: 'Policy discovery is difficult.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));

    expect(await screen.findByText('Policy discovery is difficult.')).toBeInTheDocument();
    expect(await screen.findByText('What is the title of your idea?')).toBeInTheDocument();
  });

  it('offers file and audio selection and reports upload errors generically', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response({
        session_id: sessionId,
        schema_version: 'active',
        sections: [],
        status: 'in_progress',
        submitted_at: null,
        readiness: { ready: false, missing_fields: [], invalid_fields: [] },
      }))
      .mockResolvedValueOnce(response({ error: { code: 'SOURCE_INVALID', message: 'This source could not be processed.' } }, 400));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    const input = await screen.findByLabelText(/choose a document or audio file/i);
    await waitFor(() => expect(input).not.toBeDisabled());
    fireEvent.change(input, { target: { files: [new File(['bad'], 'private-name.pdf', { type: 'application/pdf' })] } });

    expect(await screen.findByText('This source could not be processed.')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(screen.queryByText('private-name.pdf')).not.toBeInTheDocument();
  });
});