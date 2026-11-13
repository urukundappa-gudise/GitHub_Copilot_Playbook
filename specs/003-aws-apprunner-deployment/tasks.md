---
description: "Phased implementation tasks for AWS App Runner deployment"
---

# Tasks: AWS App Runner Deployment

**Input**: Design documents from `specs/003-aws-apprunner-deployment/`

**Prerequisites**: `spec.md` and `plan.md`

**Organization**: Tasks are ordered by dependency and grouped by the deployment
user stories. Tests are included for routing, build, and security behaviors
called out in the specification and plan.

**Demo identity decision**: `AUTH_REQUIRED=false` with the existing default
`employee-1` subject is intentional for cohort evaluation. It is a shared,
unauthenticated demo identity, not production user isolation. Use synthetic,
non-sensitive data only.

## Phase 1: Foundational Security and Context Boundary

**Purpose**: Establish exclusions and close the public-host origin policy before
the service is exposed.

- [x] T001 [P] [US3] Add `.env*`, local database, and SQLite file exclusions to `.copilotignore`; align the existing `.dockerignore` and add a contract assertion that these files are excluded from both contexts.
- [x] T002 [P] [US1] Add failing HTTP and WebSocket origin-policy tests in `backend/tests/contract/api/test_origin_policy.py` for exact `APP_ORIGIN`, comma-separated `ALLOWED_ORIGINS`, acceptance of sibling `*.awsapprunner.com` origins, Origin authority matching the request Host, and rejection of missing, malformed, `null`, unrelated, and deceptive-suffix origins; mark the sibling-origin allowance as cohort-demo-only in test/feature documentation.
- [x] T003 [US1] Update `is_origin_allowed` and its HTTP/WebSocket call sites in `backend/src/aimplify_intake/api/app.py` to evaluate configured exact origins, App Runner hostname suffixes, and request-host matches while retaining default denial for other origins.

**Checkpoint**: App Runner same-origin requests are accepted without a wildcard for arbitrary domains; unrelated origins remain denied.

## Phase 2: User Story 1 - Use the Application from One Public Service (Priority: P1)

**Goal**: Serve the compiled frontend, static assets, and existing API from one
FastAPI container.

**Independent Test**: A production container returns the frontend and assets,
serves API/health routes as FastAPI responses, and supports a client-side route.

- [x] T004 [P] [US1] Add route tests in `backend/tests/integration/test_frontend_serving.py` for `/`, built assets, client-side navigation fallback, unknown API/static paths, `/health/live`, and existing WebSocket routing; assert fallback never returns frontend HTML for API or health paths.
- [x] T005 [US1] Serve the built `frontend/dist` files and browser-route fallback from `backend/src/aimplify_intake/api/app.py`; keep API, WebSocket, health, and missing-asset behavior distinct and allow tests to construct the app without a frontend build.
- [x] T006 [US1] Add a root `Dockerfile` with Node and Python build stages and a minimal Python 3.11 runtime stage; install the backend from `backend/pyproject.toml`, copy `frontend/dist`, run as non-root, and bind Uvicorn to `0.0.0.0:8000`.
- [x] T007 [US1] Add a CI image build and container smoke check in `.github/workflows/ci.yml` that starts the image without AWS credentials or a remote database and verifies `/`, `/health/live`, and API route separation on port 8000.

**Checkpoint**: One locally runnable image serves frontend, API, health, and WebSocket routes on port 8000.

## Phase 3: User Story 2 - Run the Demo without Managed Database Resources (Priority: P1)

**Goal**: Preserve the existing in-memory SQLite default and explicitly configure
the intended shared cohort-evaluation identity.

**Independent Test**: Start the container without `DATABASE_URL`; create and read
a demo session in-process, and verify demo-mode configuration is documented.

- [x] T008 [P] [US2] Add or extend a container/backend smoke test in `backend/tests/integration/test_apprunner_demo_mode.py` to assert that with `AUTH_REQUIRED=false` and no identity verifier, requests use the shared default `employee-1` subject; an unset `DATABASE_URL` uses in-memory SQLite and supports session creation and readback within the running process.
- [x] T009 [US2] Configure `AUTH_REQUIRED=false` and omit `DATABASE_URL` in `deploy/apprunner/main.tf`; document that all cohort participants use the shared default `employee-1` subject and must submit synthetic, non-sensitive data.

**Checkpoint**: The App Runner runtime requires no RDS or VPC connector and makes no durability or user-isolation claim.

## Phase 4: User Story 3 - Publish through Federated CI/CD (Priority: P1)

**Goal**: Provision the deployment prerequisites once, then make every workflow
deployment push an immutable image before creating or updating App Runner.

**Independent Test**: An authorized workflow identity pushes a SHA-tagged image;
the service deployment phase consumes that exact tag. A failed push prevents
service create/update.

- [x] T010 [US3] Add one-time bootstrap Terraform under `deploy/bootstrap/` for the ECR repository, GitHub OIDC deployment role/trust, App Runner ECR access role, and scoped policies; accept repository/ref/environment inputs and document the operator-provisioned Terraform state backend. Separate create-time App Runner permissions from update-time permissions; constrain create to the configured service name/resource pattern where supported, and document any unavoidable wildcard action with available region/account/service-name conditions.
- [x] T011 [US3] Add App Runner service Terraform under `deploy/apprunner/` that accepts the ECR image tag, uses the bootstrap ECR access role, configures public ingress, port 8000, `/health/live`, one-instance demo scaling, runtime settings, and service URL output.
- [x] T012 [US3] Add Phase A to `.github/workflows/cd.yml`: require an authorized deployment ref, grant only `contents: read` and `id-token: write` as needed, assume the scoped AWS role through OIDC, build the root `Dockerfile`, and push the immutable `${{ github.sha }}` image tag to the pre-provisioned ECR repository.
- [x] T013 [US3] Add Phase B to `.github/workflows/cd.yml`, dependent on successful Phase A: run Terraform for `deploy/apprunner/` with the exact pushed image tag, create the service on first deployment or update it thereafter, wait for a healthy deployment, and report the AWS-assigned HTTPS URL.
- [x] T014 [US3] Add deployment-policy checks in `backend/tests/contract/test_apprunner_deployment.py` or the existing cloud-identity CI checks to verify the workflow has no static AWS credentials, its OIDC trust is repository/ref scoped, create-time and update-time IAM actions are separately constrained, `iam:PassRole` is limited to the ECR access role, state access is scoped, and Phase B cannot run after a failed Phase A.

**Checkpoint**: First deployment and subsequent updates use the same Phase A then Phase B sequence; no service update references an image that was not pushed successfully.

## Phase 5: User Story 4 - Access a Healthy Public HTTPS Demo (Priority: P1)

**Goal**: Provide operators a repeatable bootstrap/deploy procedure and verify
the AWS-generated public service URL.

**Independent Test**: After AWS prerequisites are provisioned, the service
reaches `RUNNING`, passes health checks, and serves the frontend over HTTPS.

- [x] T015 [P] [US4] Write `deploy/apprunner/README.md` with one-time bootstrap order, required GitHub variables, OIDC trust configuration, Phase A/Phase B deployment flow, Terraform state prerequisites, URL retrieval, SQLite data-loss limits, shared demo identity warning, and teardown steps.
- [x] T016 [US4] Add a post-deployment verification procedure to `deploy/apprunner/README.md` that checks the generated App Runner HTTPS URL, frontend, `/health/live`, same-origin API requests, and service health; record live AWS verification as an operator release gate rather than a local CI claim.

**Checkpoint**: A maintainer can provision prerequisites, deploy through OIDC, retrieve the actual service URL, and verify the live demo without static AWS credentials.

## Phase 6: Cross-Cutting Validation

**Purpose**: Preserve existing application gates and validate container, IaC,
and CI/CD behavior before deployment.

- [x] T017 [P] Run backend pytest and golden evaluation, frontend tests/typecheck/build, and the new origin-policy/static-serving tests; resolve regressions without weakening existing gates.
- [ ] T018 [P] Run `terraform fmt -check` and `terraform validate` for `deploy/bootstrap/` and `deploy/apprunner/`; inspect plans for scoped IAM, public App Runner ingress, the expected image tag, port 8000, health path, and one-instance demo scaling.
- [ ] T019 Build and inspect the final runtime image; verify it contains the frontend and backend, runs non-root, exposes port 8000, and excludes `.env*`, local database files, credentials, and build caches.

**Local validation limitation**: Terraform format/validation passed, but T018's authenticated AWS plan could not be generated because AWS account resources are operator-provisioned. T019 could not be run because this machine has no Docker/Podman runtime or WSL installation; the new CI Terraform and container-smoke jobs cover those repeatable checks. Live AWS deployment and URL verification remain operator-gated.

## Dependencies and Execution Order

- **Phase 1**: T001 and T002 may run in parallel; T003 depends on T002.
- **Phase 2**: T004 precedes T005; T006 depends on the static asset location established by T005; T007 depends on T006.
- **Phase 3**: T008 and T009 may proceed independently after the runtime config path is defined; the App Runner service task T011 applies the runtime settings.
- **Phase 4**: T010 must complete before T012 because the ECR repository and OIDC role must exist before the workflow can push. T011 defines the service consumed in Phase B. T012 must complete successfully before T013; T014 validates the finished workflow and trust configuration.
- **Phase 5**: T015 can proceed alongside IaC work; T016 depends on the deployed service and requires AWS operator access.
- **Phase 6**: T017-T019 follow implementation; T019 depends on the final Dockerfile and exclusions.

## Parallel Opportunities

- T001 and T002 are independent foundational changes.
- T004 can be authored while the origin guard in T003 is implemented because they target separate test and source files.
- T008 and T009 may proceed in parallel; T015 documentation can also start while Terraform is being built.
- The backend/frontend regression suite, Terraform validation, and image inspection are independent final checks once their implementation dependencies are complete.

## Implementation Strategy

1. Complete the context-boundary and origin-policy tasks first; verify the new origin tests fail before the guard change and pass afterward.
2. Implement FastAPI static serving, then build and smoke-test the unified image locally.
3. Configure the intentional cohort demo mode and confirm the SQLite-only startup path.
4. Provision the one-time ECR/OIDC prerequisites. The App Runner service is not created until the deployment workflow has pushed its initial image.
5. Run the workflow's Phase A image push, then Phase B Terraform create/update and health wait. Verify the generated URL in AWS.
6. Complete regression, security, IaC, image-content, and live deployment gates before marking the feature complete.

## Notes

- `[P]` indicates independent work on separate files; user-story labels map to `spec.md`.
- ECR and the OIDC deployment role must be bootstrapped before the workflow's first Phase A. Terraform state storage is a separate operator prerequisite.
- The App Runner service is intentionally public and uses a shared unauthenticated demo subject. This is acceptable only for the cohort evaluation demo with synthetic, non-sensitive input; it is not production identity or per-user isolation.
- Live AWS deployment and URL verification require an AWS account and configured GitHub environment; local CI cannot claim that gate passed.