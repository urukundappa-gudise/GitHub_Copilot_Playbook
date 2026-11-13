import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { getAuthSession } from '../services/auth';
import { AuthenticationStatus } from '../components/AuthenticationStatus';

vi.mock('../services/auth', () => ({
  getAuthSession: vi.fn(),
  signInUrl: '/api/v1/auth/login',
}));

const authSession = vi.mocked(getAuthSession);

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('authentication status', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('shows an accessible sign-in action and safe loading/error states', () => {
    const { rerender } = render(
      <AuthenticationStatus required loading user={null} error="" />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(/checking sign-in/i);

    rerender(
      <AuthenticationStatus required loading={false} user={null} error="" />,
    );
    expect(
      screen.getByRole('link', { name: /sign in with infovision sso/i }),
    ).toHaveAttribute('href', '/api/v1/auth/login');

    rerender(
      <AuthenticationStatus
        required
        loading={false}
        user={null}
        error="Sign-in could not be completed. Please try again."
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/please try again/i);
  });

  it('shows verified employee profile and a POST logout navigation', () => {
    render(
      <AuthenticationStatus
        required
        loading={false}
        user={{
          oid: 'employee-oid',
          upn: 'employee@infovision.example',
          email: 'employee@infovision.example',
          name: 'Employee Name',
        }}
        error=""
      />,
    );
    expect(screen.getByText('Employee Name')).toBeInTheDocument();
    expect(screen.getByText('employee@infovision.example')).toBeInTheDocument();
    expect(screen.getByLabelText('Employee avatar')).toHaveTextContent('EN');
    expect(screen.getByRole('button', { name: /log out/i }).closest('form')).toHaveAttribute(
      'action',
      '/api/v1/auth/logout',
    );
    expect(screen.getByRole('button', { name: /log out/i }).closest('form')).toHaveAttribute(
      'method',
      'post',
    );
  });
});

describe('authenticated intake bootstrap', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('does not open or enable an intake for an unauthenticated required-auth session', async () => {
    authSession.mockResolvedValue({ required: true, user: null });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    expect(
      await screen.findByRole('link', { name: /sign in with infovision sso/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /message/i })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('opens the intake only after authenticated identity bootstrap', async () => {
    authSession.mockResolvedValue({
      required: true,
      user: {
        oid: 'employee-oid',
        upn: 'employee@infovision.example',
        email: null,
        name: 'Employee Name',
      },
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({
        session_id: 'authenticated-session',
        status: 'in_progress',
        schema_version: 'active',
      }, 201))
      .mockResolvedValueOnce(response({
        session_id: 'authenticated-session',
        schema_version: 'active',
        sections: [],
        status: 'in_progress',
      }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    await waitFor(() => expect(screen.getByRole('textbox', { name: /message/i })).toBeEnabled());
    expect(screen.getByText('Employee Name')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('fails closed when session bootstrap cannot be verified', async () => {
    authSession.mockRejectedValue(new Error('network failure'));
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /authentication could not be verified/i,
    );
    expect(screen.getByRole('textbox', { name: /message/i })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
