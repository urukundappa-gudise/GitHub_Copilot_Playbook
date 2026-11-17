import { signInUrl } from '../services/auth';

export function LoginPage() {
  const signInFailed = new URLSearchParams(window.location.search).get('auth') === 'error';

  return (
    <main className="login-page">
      <header className="login-topbar">
        <a className="brand" href="/" aria-label="AIMPLIFY home">
          <span className="brand-mark" aria-hidden="true">A</span>
          <span>AIMPLIFY <small>IDEA INTAKE</small></span>
        </a>
        <span className="login-topbar-label">EMPLOYEE ACCESS</span>
      </header>
      <section className="login-layout" aria-labelledby="login-title">
        <div className="login-copy">
          <p className="eyebrow">INFOVISION / SECURE WORKSPACE</p>
          <h1 id="login-title">Sign in to AIMPLIFY</h1>
        </div>
        <div className="login-panel">
          <p className="login-panel-label">CORPORATE ACCOUNT</p>
          {signInFailed && (
            <p className="login-error" role="alert">
              Sign-in could not be completed. Please try again.
            </p>
          )}
          <a className="login-sso-button" href={signInUrl}>
            Sign in with InfoVision SSO
          </a>
          <p className="login-security-note">Authentication is handled securely by Microsoft Entra ID.</p>
          <a className="login-back-link" href="/">Back to intake</a>
        </div>
      </section>
      <footer className="login-footer">
        <span>AIMPLIFY</span>
        <span>InfoVision employee sign-in</span>
      </footer>
    </main>
  );
}