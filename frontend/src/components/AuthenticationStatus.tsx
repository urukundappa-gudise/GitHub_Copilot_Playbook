import { AuthUser, signInUrl } from '../services/auth';

type Props = {
  required: boolean;
  loading: boolean;
  user: AuthUser | null;
  error: string;
};

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] ?? '')
    .join('')
    .toUpperCase();
}

export function AuthenticationStatus({ required, loading, user, error }: Props) {
  if (!required && !loading && !user && !error) return null;
  if (loading) {
    return <div className="authentication-status" role="status">Checking sign-in…</div>;
  }
  if (!user) {
    return (
      <div className="authentication-status">
        {error && <p className="error-message" role="alert">{error}</p>}
        {required && (
          <a className="sign-in-button" href={signInUrl}>
            Sign in with InfoVision SSO
          </a>
        )}
      </div>
    );
  }
  return (
    <div className="authentication-status" aria-label="Signed-in account">
      <span className="employee-avatar" aria-label="Employee avatar" role="img">
        {initials(user.name)}
      </span>
      <span className="employee-profile">
        <strong>{user.name}</strong>
        <small>{user.upn}</small>
      </span>
      <form method="post" action="/api/v1/auth/logout">
        <button type="submit" className="logout-button">Log out</button>
      </form>
    </div>
  );
}
