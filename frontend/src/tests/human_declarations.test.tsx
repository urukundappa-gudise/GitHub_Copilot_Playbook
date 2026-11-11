import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { HumanDeclarations } from '../components/HumanDeclarations';

const sessionId = 'session-human-fields';
const humanFields = [
  { field_key: 'declaration_accepted', mandatory: true, human_only: true },
  { field_key: 'submitter_signature', mandatory: true, human_only: true },
  { field_key: 'date_of_submission', mandatory: true, human_only: true },
  { field_key: 'reviewer_notes', mandatory: false, human_only: true },
];

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('human declarations', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('keeps saves busy after one sibling fails and suppresses callbacks after unmount', async () => {
    let finish: (value: Response) => void = () => { throw new Error('Pending save not started'); };
    const pending = new Promise<Response>((resolve) => { finish = resolve; });
    vi.stubGlobal('fetch', vi.fn()
      .mockRejectedValueOnce(new Error('one save failed'))
      .mockReturnValueOnce(pending)
      .mockReturnValueOnce(pending));
    const saved = vi.fn();
    const busy = vi.fn();
    const view = render(<HumanDeclarations sessionId={sessionId} fields={humanFields} onSaved={saved} onBusyChange={busy} />);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText(/submitter signature/i), { target: { value: 'Example' } });
    fireEvent.change(screen.getByLabelText(/date of submission/i), { target: { value: '2026-11-11' } });
    const form = screen.getByRole('button', { name: /save declaration/i }).closest('form');
    if (!form) throw new Error('Declaration form missing');
    fireEvent.submit(form);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole('button', { name: /save declaration/i })).toBeDisabled();
    expect(busy).toHaveBeenLastCalledWith(true);
    view.unmount();
    await act(async () => {
      finish(response({ field_key: 'submitter_signature', value: 'Example', origin: 'human_entered' }));
    });
    expect(saved).not.toHaveBeenCalled();
  });

  it('keeps AI updates out of human controls and saves explicit human input', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ session_id: sessionId, status: 'in_progress', schema_version: 'active' }, 201))
      .mockResolvedValueOnce(response({
        session_id: sessionId,
        schema_version: 'active',
        sections: [{ section_key: 'section_06', fields: humanFields }],
        status: 'in_progress',
        submitted_at: null,
        readiness: { ready: false, missing_fields: [], invalid_fields: [] },
      }))
      .mockResolvedValueOnce(response({
        request_id: 'request-ai-fields',
        field_updates: humanFields.map((field) => ({
          field_key: field.field_key,
          value: 'AI suggestion',
          origin: 'ai_extracted',
        })),
        clarification: null,
        status: 'in_progress',
      }))
      .mockImplementation(() => Promise.resolve(response({
        field_key: 'human-field',
        value: 'saved',
        origin: 'human_entered',
      })));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    const declaration = await screen.findByRole('checkbox', { name: /declaration accepted/i });
    const signature = screen.getByRole('textbox', { name: /submitter signature/i });
    expect(screen.getByLabelText(/date of submission/i)).toHaveAttribute('type', 'date');
    const notes = screen.getByRole('textbox', { name: /additional notes for reviewer/i });

    fireEvent.change(screen.getByRole('textbox', { name: /message/i }), {
      target: { value: 'Please complete my declaration.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => expect(declaration).not.toBeChecked());
    expect(signature).toHaveValue('');
    expect(notes).toHaveValue('');

    fireEvent.click(declaration);
    fireEvent.change(signature, { target: { value: 'Jordan Lee' } });
    fireEvent.change(screen.getByLabelText(/date of submission/i), {
      target: { value: '2026-11-04' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save declaration/i }));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url, init]) =>
      String(url).includes('/fields/') && init?.method === 'PUT',
    )).toHaveLength(3));
    fireEvent.change(notes, { target: { value: 'Please review this idea.' } });
    fireEvent.click(screen.getByRole('button', { name: /save reviewer notes/i }));

    await waitFor(() => expect(fetchMock.mock.calls.filter(([url, init]) =>
      String(url).includes('/fields/') && init?.method === 'PUT',
    )).toHaveLength(4));
    const savedRequests = fetchMock.mock.calls.filter(([url, init]) =>
      String(url).includes('/fields/') && init?.method === 'PUT',
    );
    expect(savedRequests.map(([url]) => String(url).split('/').pop())).toEqual([
      'declaration_accepted',
      'submitter_signature',
      'date_of_submission',
      'reviewer_notes',
    ]);
    expect(savedRequests.every(([, init]) => JSON.parse(String(init?.body)).value !== 'AI suggestion')).toBe(true);
  });
});