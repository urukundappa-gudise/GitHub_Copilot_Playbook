import { render, screen } from '@testing-library/react';
import { afterEach, vi } from 'vitest';
import App from './App';

describe('App', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('renders the intake application heading', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ session_id: 'session-test', status: 'in_progress', schema_version: 'active' }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        session_id: 'session-test',
        schema_version: 'active',
        sections: [],
        status: 'in_progress',
        submitted_at: null,
        readiness: { ready: false, missing_fields: [], invalid_fields: [] },
      }))));
    render(<App />);

    await screen.findByRole('textbox', { name: /message/i });
    expect(screen.getByRole('heading', { name: /tell us about your idea/i })).toBeInTheDocument();
  });
});
