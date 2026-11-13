# Data Model: InfoVision SSO Login

This feature adds authentication records to the existing SQLAlchemy persistence boundary. It does not modify the canonical intake schema, submission values, or human-only fields.

## Employee Identity

Represents claims accepted only after the OIDC client validates the Entra response.

| Field | Type | Rules |
|---|---|---|
| `oid` | string | Required, non-empty, stable Entra object identifier; used as `subject_ref` and `IdentityVerifier.subject`. |
| `upn` | string | Required employee sign-in name; display/contact claim only, not an authorization key. |
| `email` | string or null | Optional. Preserve the validated claim when present; store null when Entra omits it. Its absence does not block sign-in, and it is never an authorization key. |
| `name` | string | Required display name from validated claims. |

The frontend receives only the fields required to display the signed-in employee. It cannot provide or override these values when creating an intake session.

## OIDC Login Transaction

Represents one pending authorization attempt. It is not an authenticated user session.

| Field | Type | Rules |
|---|---|---|
| `transaction_id` | random string | Internal identifier; not accepted as identity. |
| `state_digest` | string | Digest of unpredictable state sent in the authorization request; compared and consumed once. |
| `nonce` | string | Unpredictable value bound to the request and checked against the validated ID token. |
| `pkce_verifier` | string | S256 verifier bound to this authorization attempt; used only when redeeming its code. |
| `created_at` | timestamp | Set by the service. |
| `expires_at` | timestamp | Ten minutes after creation by default; expired transactions cannot be used. |
| `consumed_at` | timestamp or null | Set atomically when callback processing begins; a consumed transaction cannot be replayed. |

Callback validation requires a matching, unexpired, unconsumed transaction and successful code redemption. Delete the transaction after completion or expiry. Do not log or return its values. Database access and backups must follow the configured secret/PII protection policy.

## OIDC Application Session

Represents the local authenticated session presented as `oidc_session`.

| Field | Type | Rules |
|---|---|---|
| `session_id` | random string | Internal primary key. |
| `token_digest` | string | Unique digest of the random opaque cookie token; the raw cookie value is never persisted. |
| `subject_ref` | string | Validated Entra `oid`; immutable authorization subject. |
| `upn` | string | Validated profile claim. |
| `email` | string or null | Optional validated email claim; null when absent and not a sign-in failure. |
| `name` | string | Validated display-name claim. |
| `created_at` | timestamp | Set when the verified callback creates the session. |
| `expires_at` | timestamp | No later than eight hours after creation by default. |
| `revoked_at` | timestamp or null | Set on logout; revoked records fail every later verifier lookup. |

The cookie uses `HttpOnly`, `Secure`, `SameSite=Lax`, path `/`, and no broad domain attribute. It is cleared with matching attributes at logout. Expired and revoked records are invalid. No Entra access token, refresh token, or ID token is retained as the application session.

## Authentication Policy

| Setting | Meaning |
|---|---|
| `AUTH_REQUIRED` | When true, all intake HTTP and WebSocket access requires an active session resolved by `IdentityVerifier`. |
| `AZURE_AD_TENANT_ID` | Selects the tenant-specific OIDC authority and discovery metadata. An absent value never enables production mock identity. |
| `APP_ENV` | Separates local/test from production runtime policy. |
| `AUTH_MOCK_MODE` | Explicit test/local-only mock toggle; allowed only when `APP_ENV` is local/test and tenant configuration is absent. |

## Relationships and State Transitions

- An Employee Identity can have multiple OIDC Application Sessions over time; each session is independently expiring and revocable.
- A login transaction may produce zero or one session. Its lifecycle is `pending -> consumed -> deleted`; expiration deletes an unconsumed transaction, and any validation failure produces no session.
- An application session transitions `active -> revoked` on logout or `active -> expired` at its expiry time. Both terminal states fail verification.
- Intake submissions continue to reference the employee `oid` as `subject_ref`; session tokens and email/UPN do not become ownership identifiers.