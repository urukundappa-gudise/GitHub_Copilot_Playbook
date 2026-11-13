# Feature Specification: AWS App Runner Deployment

**Feature Branch**: `003-aws-apprunner-deployment`

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "Deploy the AIMPLIFY application to AWS App Runner as a unified single-container service, build and push the image to ECR using GitHub Actions with AWS OIDC, and use zero-cost SQLite storage for a public live demo."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Use the application from one public service (Priority: P1)

A demo user opens the App Runner service URL and receives the React intake application. The same service handles its API requests, so the demo does not depend on a separately hosted frontend or a cross-origin API service.

**Why this priority**: A working, public, single-origin demo is the primary outcome of deployment.

**Independent Test**: Build and run the production container, load `/`, and exercise an intake API request through `/api/v1/` on the same origin.

**Acceptance Scenarios**:

```gherkin
Scenario: Serve the built frontend from the API service
  Given the production container contains the compiled React frontend and FastAPI backend
  When a user requests the service root path
  Then the service returns the compiled frontend application
  And frontend assets are served by the same container
  And the frontend can call the intake API on the same origin
```

```gherkin
Scenario: Keep frontend navigation and API routes distinct
  Given the service is running
  When a user loads a frontend route or requests an intake API route
  Then frontend routes resolve to the frontend application entry point
  And API requests under /api/v1/ are handled by FastAPI rather than the frontend fallback
```

```gherkin
Scenario: Accept explicitly configured origins
  Given the service receives an HTTP request or WebSocket handshake
  When Origin exactly matches APP_ORIGIN or an ALLOWED_ORIGINS entry
  Then the origin guard allows the request

Scenario: Accept App Runner service origins
  Given the service receives an HTTP request or WebSocket handshake
  When Origin has a hostname ending in .awsapprunner.com
  Then the origin guard allows the request

Scenario: Accept a same-host origin
  Given the service receives an HTTP request or WebSocket handshake
  When Origin authority matches the request Host
  Then the origin guard allows the request

Scenario: Reject missing or unapproved origins
  Given the service receives an HTTP request or WebSocket handshake
  When Origin is missing, malformed, null, or otherwise unapproved
  Then the origin guard denies the request
```

### User Story 2 - Run a cost-conscious demo without managed database resources (Priority: P1)

A maintainer deploys the demo without provisioning Amazon RDS or configuring a VPC connector. The service uses SQLite in memory or a local file, with its persistence limits made clear to demo users and operators.

**Why this priority**: Avoiding a paid database and private-network dependency is an explicit deployment constraint.

**Independent Test**: Start the container without a remote database URL or VPC access and verify that the application becomes healthy and can create and read a demo intake session.

**Acceptance Scenarios**:

```gherkin
Scenario: Start with SQLite and no external database
  Given the container has no DATABASE_URL configured
  When the application starts
  Then it uses the configured SQLite in-memory or local-file database
  And it does not require Amazon RDS, a VPC connector, or a database network endpoint
  And the live health endpoint returns a successful response on port 8000
```

```gherkin
Scenario: Disclose demo database persistence boundaries
  Given the service uses an in-memory database or App Runner instance-local file storage
  When an operator reviews the deployment behavior
  Then the service does not promise durable or shared records across restarts or instances
  And deployment documentation identifies the selected SQLite mode and its data-loss limitations
```

### User Story 3 - Publish a container through federated CI/CD (Priority: P1)

A maintainer merges an eligible change and GitHub Actions builds the unified image, assumes a narrowly scoped AWS role using GitHub OIDC, pushes the image to Amazon ECR, and deploys or updates the App Runner service without static AWS credentials.

**Why this priority**: Repeatable deployment and credential hygiene are necessary to operate the public demo safely.

**Independent Test**: Run the workflow for an authorized repository ref and verify that OIDC role assumption succeeds, the image is pushed to ECR, and the App Runner service runs the resulting image.

**Acceptance Scenarios**:

```gherkin
Scenario: Build and publish the image using GitHub OIDC
  Given a workflow run is authorized for the configured repository and deployment ref
  When the deployment workflow runs
  Then it builds the multi-stage Docker image with the frontend build and FastAPI backend
  And it assumes the configured AWS IAM role using GitHub OIDC
  And it pushes a traceable image to the configured Amazon ECR repository
  And it does not use static AWS access keys or secrets
```

```gherkin
Scenario: Reject unauthorized workflow identity
  Given a workflow run is from an untrusted repository, ref, or workflow identity
  When it attempts to assume the deployment role
  Then AWS denies role assumption
  And the run cannot push an image or change the App Runner service
```

```gherkin
Scenario: Exclude local secrets and databases from repository and Docker contexts
  Given the repository contains .env* files or local database files
  When Copilot gathers repository context or Docker collects its build context
  Then .copilotignore excludes .env* files and local database files from Copilot context
  And the Docker ignore configuration excludes those files from Docker build context
  And those files are not copied into any build stage or the runtime image
```

### User Story 4 - Access a healthy public HTTPS demo (Priority: P1)

A demo user follows the service's AWS-generated HTTPS URL and reaches a healthy application. The service health check targets the application on port 8000.

**Why this priority**: The deployment is useful only when App Runner exposes and monitors a reachable service.

**Independent Test**: Deploy the image to App Runner, obtain the service URL from AWS, and verify HTTPS access to `/` and a successful health check.

**Acceptance Scenarios**:

```gherkin
Scenario: Create a publicly reachable App Runner service
  Given a valid App Runner configuration and image in ECR
  When the service deployment completes
  Then App Runner provides an automatic public HTTPS URL in the form https://<service-id>.<region>.awsapprunner.com
  And the URL serves the frontend over HTTPS
  And the service health check uses port 8000 and /health/live or /api/v1/health
```

```gherkin
Scenario: Replace an unhealthy deployment
  Given an image that does not start or does not respond successfully at the configured health path
  When App Runner evaluates the deployment health check
  Then the deployment is not reported as healthy
  And the failure is visible to the maintainer
```

```gherkin
Scenario: Use the shared identity for the cohort evaluation demo
  Given the public cohort demo is configured with AUTH_REQUIRED=false
  And no identity verifier is configured
  When a participant creates or accesses an intake session
  Then the existing default employee-1 subject is used
  And deployment documentation states that this identity is shared and not production user isolation
  And the demo is limited to synthetic, non-sensitive data
```

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The deployment MUST use a multi-stage Dockerfile that builds the React frontend into `frontend/dist` and packages the FastAPI backend from `backend/src/aimplify_intake/` into a single runtime image.
- **FR-002**: The runtime image MUST start FastAPI on port `8000` and serve the compiled frontend at `/` from the same container.
- **FR-003**: The frontend MUST use same-origin API requests to the existing `/api/v1/` API. Frontend route fallback MUST NOT intercept API or health routes.
- **FR-004**: The deployment MUST provide an App Runner configuration specification as `apprunner.yaml` or Terraform. It MUST define the image source, port `8000`, health check path `/health/live` or `/api/v1/health`, and required runtime configuration.
- **FR-005**: The application MUST support SQLite through `sqlite+pysqlite:///:memory:` or a local SQLite file and MUST NOT require Amazon RDS, a paid database, or an App Runner VPC connector for the demo deployment.
- **FR-006**: Deployment documentation MUST state that in-memory and App Runner instance-local SQLite data is not durable or shared across instance replacement, restart, or scale-out. The demo MUST NOT promise durable data retention.
- **FR-007**: The repository MUST provide `.github/workflows/cd.yml` to build and push the runtime image to Amazon ECR and deploy or update the configured App Runner service.
- **FR-008**: The deployment workflow MUST obtain AWS credentials by assuming an IAM role through GitHub Actions OIDC. It MUST NOT use static AWS access keys, long-lived AWS credentials, or equivalent stored cloud credentials.
- **FR-009**: The AWS role trust and permissions MUST be limited to the intended GitHub repository, workflow/ref, ECR image push, and the App Runner deployment actions required by the selected deployment method.
- **FR-010**: `.copilotignore` MUST exclude `.env*` files and local database files from Copilot context. Docker's build-context ignore configuration MUST exclude the same files from image builds, and those files MUST NOT be included in any build stage or the runtime image.
- **FR-011**: The deployed App Runner service MUST expose its AWS-assigned public HTTPS service URL for the live demo; the URL MUST NOT be represented as a fixed value before AWS provisions the service.
- **FR-012**: The container MUST provide a successful live health response at `/health/live` or `/api/v1/health` on port `8000` when the service is ready to accept requests.
- **FR-013**: CI/CD MUST use an immutable or traceable image reference so the deployed App Runner revision can be associated with the source commit that produced it.
- **FR-014**: The origin guard MUST allow exact origins configured by `APP_ORIGIN` or `ALLOWED_ORIGINS`, origins whose hostname ends in `.awsapprunner.com`, and requests where Origin authority matches the request Host. It MUST deny missing, malformed, `null`, and other unapproved origins for HTTP and WebSocket requests.
- **FR-015**: The cohort evaluation demo MUST configure `AUTH_REQUIRED=false` and use the existing `employee-1` fallback subject when no identity verifier is configured. Deployment documentation MUST identify this as shared, non-production identity and restrict demo use to synthetic, non-sensitive data.

### Key Entities

- **Unified Runtime Image**: A single container image containing the built React application and FastAPI backend.
- **App Runner Service**: The AWS-managed public HTTPS service running the unified image and configured health check.
- **Deployment Role**: The IAM role assumed by GitHub Actions through OIDC with repository- and workflow-scoped trust.
- **SQLite Demo Store**: The in-memory or instance-local database used without a managed database or VPC connector; it does not guarantee durable or shared data.
- **Build Context Boundary**: The files available to Docker during image construction, with local secrets and database files excluded.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A clean production image build produces one runnable runtime image containing both `frontend/dist` and the FastAPI application.
- **SC-002**: A production container started without a remote database or VPC connection returns the frontend at `/`, serves the existing intake API under `/api/v1/`, and passes its configured health check on port `8000`.
- **SC-003**: An App Runner deployment is healthy and reachable over AWS-provisioned HTTPS at the AWS-assigned service URL.
- **SC-004**: An authorized GitHub Actions run pushes a source-traceable image to ECR and deploys it without static AWS credentials; an unauthorized workflow identity cannot assume the deployment role.
- **SC-005**: Automated inspection of the Docker build context and runtime image finds no `.env*` files or local database files.
- **SC-006**: No RDS instance or VPC connector is required for the specified demo deployment.
- **SC-007**: Deployment documentation clearly communicates SQLite data loss and non-sharing behavior across restarts, replacements, or multiple instances.

## Assumptions

- The existing FastAPI `/health/live` endpoint and `/api/v1/` intake routes remain the health and API contract unless implementation evidence requires a compatibility-preserving adjustment.
- App Runner's AWS-managed public service URL is generated only after service creation; documentation and workflow outputs can report the actual URL after provisioning.
- SQLite is suitable only for a zero-cost demo. Durable multi-instance production persistence is outside this feature's scope.
- The frontend will be built into `frontend/dist`; a static-file mount and SPA fallback may be added to the backend without changing the existing API contract.
- GitHub repository, AWS account, region, ECR repository, IAM role, and App Runner service configuration values are deployment inputs supplied by maintainers, not credentials committed to the repository.
- `.copilotignore` controls Copilot context only; Docker's own ignore configuration is also required to prevent the files from entering the Docker build context.
- The cohort evaluation demo intentionally uses `AUTH_REQUIRED=false` and the existing shared `employee-1` subject; it does not provide production authentication or user isolation and is limited to synthetic, non-sensitive data.
- The App Runner hostname origin rule intentionally accepts origins from other `*.awsapprunner.com` services. This broad origin trust is acceptable only for the public cohort demo and MUST NOT be reused as a production origin policy.