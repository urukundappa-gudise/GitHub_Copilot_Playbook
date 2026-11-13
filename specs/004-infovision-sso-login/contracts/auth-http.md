# HTTP Contract: InfoVision OIDC Authentication

All authentication routes are same-origin under `/api/v1/auth`. No endpoint returns an Entra access, refresh, or ID token to the browser. Authentication errors use the existing generic API error shape and do not echo callback values or provider error descriptions.

## `GET /api/v1/auth/login`

Begins an Entra Authorization Code Flow with PKCE S256 and redirects the browser to the tenant-specific authorization endpoint.

- Creates a random state, nonce, and PKCE verifier, and persists a short-lived transaction before redirecting.
- Requests the OIDC scopes needed for employee identity (`openid`, `profile`, and `email`).
- The redirect includes the S256 challenge, state, and nonce; it does not include credentials or employee PII.
- If tenant/client/callback configuration is missing, production fails closed with a safe error response. An explicitly enabled local/test mock can be used only when the tenant is unset.

**302 response**: `Location` points to the Entra authorization endpoint.

## `GET /api/v1/auth/callback`

Accepts the authorization response and completes login.

| Query parameter | Required | Behavior |
|---|---|---|
| `code` | Yes, absent provider error | Redeemed only with the matching transaction's PKCE verifier. |
| `state` | Yes | Must match an unexpired, unconsumed transaction. |
| `error` | Provider response | Reject login; present a generic recoverable failure after redirect. |

On success, validate the ID token and required `oid`, `upn`, and `name` claims using provider metadata/JWKS and the transaction nonce. Use `oid` as the stable subject. Include the validated `email` claim when present and set it to null when absent; missing email alone MUST NOT reject sign-in. Create an expiring local session, store only the digest of its random cookie token, set `oidc_session`, and redirect to the application root.

**Cookie**: `HttpOnly; Secure; SameSite=Lax; Path=/`, with an expiry no longer than the configured session lifetime. A failed or replayed callback MUST NOT set a session cookie.

## `GET /api/v1/auth/session`

Returns current verified identity for frontend rendering. Response MUST be `Cache-Control: no-store`.

**200 response**

Headers: `Cache-Control: no-store`; `X-Authentication-Required` is `true` when the deployment requires sign-in and `false` when authentication is optional.

```json
{
  "authenticated": true,
  "user": {
    "oid": "verified-employee-object-id",
    "upn": "employee@infovision.example",
    "email": "employee@infovision.example",
    "name": "Employee Name"
  }
}
```

The `email` value is null when no validated email claim is available. An absent, invalid, expired, or revoked cookie returns `401` with the existing generic `UNAUTHENTICATED` error shape. The endpoint never returns raw tokens or internal session identifiers.

**401 response**: Includes `Cache-Control: no-store` and the same `X-Authentication-Required` header so the frontend can distinguish an unauthenticated required-auth deployment from an optional-auth demo.

## `POST /api/v1/auth/logout`

Requires a same-origin request and validates the configured Origin policy. Revokes the active local session, clears `oidc_session` with matching cookie attributes, and redirects the browser to the Entra `end_session_endpoint`. The registered post-logout redirect returns the browser to the application.

- Local revocation and cookie clearing happen even if the provider logout endpoint is unavailable afterward.
- A repeated logout is safe and leaves no active local session.
- The frontend submits this as a browser navigation/form POST; it must not rely on an XHR redirect to navigate the user to Entra.

## Intake Authorization Contract

When `AUTH_REQUIRED=true`, all existing intake HTTP routes and WebSocket handshakes require an active session. The backend resolves the cookie through `IdentityVerifier`, derives the employee subject from validated `oid`, and performs existing subject-scoped authorization. Missing/invalid/expired/revoked sessions receive the existing unauthenticated outcome; they never fall back to `employee-1` in production.

## Logging and Cache Rules

Never log cookies, ID/access/refresh tokens, codes, callback query strings, claims, state, nonce, or PKCE values. Authentication logs may include only a generic result category and request correlation ID. Session/profile responses are not cacheable.