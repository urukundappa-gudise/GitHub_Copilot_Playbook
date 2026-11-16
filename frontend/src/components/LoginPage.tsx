import { signInUrl } from '../services/auth';

export function LoginPage() {
  const signInFailed = new URLSearchParams(window.location.search).get('auth') === 'error';

  return (
    <main className="login-page">
      <section className="login-story" aria-label="InfoVision identity">
        <a className="login-brand" href="/" aria-label="AIMPLIFY home">
          <span className="login-brand-mark" aria-hidden="true">A</span>
          <span>AIMPLIFY <small>IDEA INTAKE</small></span>
        </a>
        <div className="login-story-copy">
          <p className="login-eyebrow">INFO VISION / EMPLOYEE ACCESS</p>
          <h1>Start with your verified work identity.</h1>
          <p>One corporate sign-in protects every idea and submission in your workspace.</p>
        </div>
        <p className="login-story-foot">IDENTITY PROVIDER / MICROSOFT ENTRA ID</p>
      </section>

      <section className="login-content" aria-labelledby="login-title">
        <div className="login-content-inner">
          <span className="login-glyph" aria-hidden="true">A</span>
          <p className="eyebrow">SECURE WORKSPACE</p>
          <h2 id="login-title">Sign in to AIMPLIFY</h2>
          <p className="login-copy">Continue with your InfoVision Microsoft 365 account.</p>
          {signInFailed && (
            <p className="error-message" role="alert">
              Sign-in could not be completed. Please try again.
            </p>
          )}
          <a className="login-sso-button" href={signInUrl}>
            <span>Continue with InfoVision SSO</span>
            <span className="login-arrow" aria-hidden="true">&gt;</span>
          </a>
          <p className="login-assurance">
            Microsoft Entra verifies your identity. Your password is never entered into AIMPLIFY.
          </p>
        </div>
        <footer className="login-footer">
          <span>AIMPLIFY / IDEA INTAKE</span>
          <span>Protected by InfoVision identity</span>
        </footer>
      </section>
    </main>
  );
}
