# Feature Specification: Submission Confirmation and Safety Denial Popups

**Feature Branch**: `feat/submission-popup-and-security-feedback`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Add submission confirmation popup with form reset, and a security denial popup that displays the rejection reason when input triggers NoFacts safety gates"

**Refinement (2026-11-10)**: The employee approved a confirmation modal and a nonmodal
security denial banner, success Escape dismissal without reset, and strict ASCII email
validation with valid punycode support. These choices supersede earlier two-modal wording.

**Analysis refinement (2026-11-10)**: The employee approved an explicit Correct this input
action linking the next dispatched chat message or upload to one denial operation, and
strict IDNA2008 validation without UTS #46 or transitional mappings.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Confirm final submission and start a fresh idea (Priority: P1)

An employee explicitly submits a completed idea, receives confirmation that it was
submitted, and acknowledges the popup to start a clean intake. Sending a chat message,
uploading a source, or completing the last required field does not itself submit the idea.

**Why this priority**: Employees need an unambiguous completion step without losing a
draft or mistaking data collection for a successful submission.

**Independent Test**: Complete all mandatory information and human declarations, select
Submit, verify a confirmed submitted outcome, then acknowledge the popup and verify that
a fresh intake contains none of the previous draft's state.

**Acceptance Scenarios**:

1. **Given** all 18 mandatory fields satisfy existing validation and the employee has personally completed Declaration Accepted, Date of Submission, and Submitter Signature, **When** the employee selects Submit and submission succeeds, **Then** exactly one confirmation popup states that the idea was submitted, and the submitted idea remains available through the existing record-retention behavior.
2. **Given** required information or a human declaration is missing or invalid, **When** the employee attempts final submission, **Then** submission is prevented, the employee is told what remains to be completed, and neither a success popup nor a reset occurs.
3. **Given** the success popup is open, **When** the employee activates its acknowledgment action, **Then** a fresh intake is prepared with empty captured details, conversation, composer, selected-source controls, human declarations, clarification, errors, and popup state, and progress returns to its initial value.
4. **Given** a completed draft has not been explicitly submitted, **When** the final mandatory value is accepted or another message or upload finishes, **Then** the draft remains intact and no submission confirmation appears.
5. **Given** final submission fails or its outcome is unknown, **When** the employee receives the result, **Then** the draft remains intact, a distinct failure or outcome-unknown notice is shown, and no success popup or reset occurs.
6. **Given** a submission is pending or already confirmed, **When** the employee repeatedly activates Submit or the same result is delivered again, **Then** only one submitted idea and one confirmation are produced for that submission.
7. **Given** submission succeeded but a fresh intake cannot be prepared, **When** the employee acknowledges success, **Then** the application explains that submission succeeded but starting another idea failed, offers a retry of fresh-intake preparation only, and does not permit editing or resubmitting the old idea.
8. **Given** the success modal is open, **When** the employee presses Escape or activates Close, **Then** the modal closes without resetting, focus moves to a frozen submitted summary with a Start a new idea action, and only activating that action starts a fresh intake.
9. **Given** a required email has invalid domain or TLD syntax under the agreed email policy, **When** it is extracted or final submission is validated, **Then** it is not accepted as a valid mandatory email, required-field feedback identifies it, and no success or reset occurs.

---

### User Story 2 - Understand a NoFacts rejection and correct the input (Priority: P1)

An employee whose chat, document, or audio input produces a candidate rejected by NoFacts
sees a nonmodal security denial banner explaining why information was excluded. The explanation
does not repeat rejected claims or disclose sensitive input, and accepted details remain usable.

**Why this priority**: A visible explanation lets employees correct unsupported claims
without weakening the gate or implying their whole idea was rejected.

**Independent Test**: Exercise each existing NoFacts rejection category through chat and
supported document and audio inputs; verify the banner identifies the applicable reason,
rejected values remain absent from accepted details and records, and safe corrections work.

**Acceptance Scenarios**:

1. **Given** an extracted candidate contains an unverified number, percentage, cost, date, or word-form quantity, **When** NoFacts drops that candidate, **Then** one denial banner explains the applicable rejection category and that the information was not accepted, without displaying the rejected value.
2. **Given** an input produces both accepted and rejected candidates, **When** processing finishes, **Then** accepted candidates update the intake normally, rejected candidates do not replace previously accepted values, and the banner clearly says some information was excluded rather than claiming the entire idea was denied.
3. **Given** multiple candidates are rejected during one input operation, **When** the result is presented, **Then** one banner lists the distinct applicable reasons without creating a separate banner for each candidate.
4. **Given** the denial banner is visible, **When** the employee dismisses it, **Then** the same draft and accepted details remain available and the employee can provide corrected input without restarting the intake.
5. **Given** the employee selects Correct this input on a denial banner, **When** the next dispatched chat message or upload has at least one accepted field update, no field-validation failure, and an explicitly null safety notice, **Then** only the linked earlier banner clears; unrelated notices remain and duplicate delivery cannot restore the cleared notice.
6. **Given** input is accepted without a NoFacts rejection, or fails for a non-NoFacts reason such as an unreadable source, **When** feedback is shown, **Then** no NoFacts denial banner appears and any applicable existing validation or processing error remains distinguishable.
7. **Given** safety rejection is known but its detailed reason is unavailable, **When** feedback is shown, **Then** the banner explicitly states that NoFacts rejected information but the detailed reason is unavailable; it neither invents a category nor reports success.
8. **Given** multiple denial banners exist, **When** the employee selects Correct this input on one, **Then** a visible correction selection names that operation without rejected content and offers Cancel correction; selecting another replaces the selection, and unrelated or already-running operations cannot consume it.
9. **Given** a correction is dispatched, **When** processing fails, returns no accepted update, reports field-validation failure, has legacy-absent safety metadata, or rejects any candidate, **Then** the linked earlier banner remains, ordinary errors stay distinguishable, and a new rejection has its own banner. The employee can explicitly select a correction again; dismissed banners never reopen.

---

### User Story 3 - Operate outcome feedback accessibly (Priority: P2)

An employee using a keyboard, assistive technology, or a narrow display can read and
operate either outcome without losing their place.

**Why this priority**: Feedback must be usable by every employee, not only pointer users.

**Independent Test**: Complete both outcome journeys using only a keyboard and an assistive
technology check, then repeat at a 320-pixel-wide viewport.

**Acceptance Scenarios**:

1. **Given** the success modal opens, **When** the employee navigates by keyboard or assistive technology, **Then** its title, outcome, and actions are available, focus moves inside, navigation remains contained until dismissal, and confirmation is announced politely.
2. **Given** a denial banner appears, **When** the employee continues typing or navigating, **Then** the reason is announced as an alert without stealing focus, the rest of the draft remains operable, and normal Tab order reaches its dismiss action without a focus trap.
3. **Given** a denial banner is visible, **When** the employee activates its dismiss action or presses Escape while focus is inside the banner, **Then** it closes without changing the draft and returns focus to its initiating input if that input remains available; Escape elsewhere does not unexpectedly move focus.
4. **Given** the success modal is open, **When** the employee presses Escape or Close, **Then** it closes without reset and focus moves to the frozen summary's Start a new idea action; a background click does not dismiss or reset it.
5. **Given** the employee activates Start a new idea in the modal or frozen summary, **When** fresh preparation succeeds, **Then** focus moves to the fresh intake's first input.
6. **Given** either outcome is displayed at a 320-pixel-wide viewport or at 200% zoom, **When** the employee reads and operates it, **Then** all content and actions remain reachable without horizontal scrolling.

### Edge Cases

- An input with several rejection categories produces one readable denial banner containing each distinct reason once.
- A repeated delivery of the same input result does not reopen a dismissed denial; a new rejected input does produce new feedback.
- An older input result arriving during final submission or after reset cannot update the submitted or fresh intake.
- A rejected replacement candidate leaves any previously accepted field value unchanged.
- A lost connection during final submission is an uncertain outcome, not proof of failure or success; retry or status recovery must not create another submitted idea.
- Failure to prepare a new intake after confirmed submission is separate from failure to submit; recovery must never submit the old idea again.
- Human-entered declaration dates and other valid human-only values retain existing validation and are not newly subjected to AI-candidate NoFacts rules.
- Ordinary missing-field validation and source-processing failures must not be mislabeled as security denials.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The intake MUST provide an explicit final Submit action. Final submission MUST require all 18 mandatory fields to pass existing validation and all three human-only declarations to be completed by the employee; completing fields, chat, or uploads alone MUST NOT trigger final submission.
- **FR-002**: The system MUST distinguish a confirmed submitted idea from a ready or in-progress draft. It MUST show exactly one success popup only after a confirmed successful final submission and MUST preserve the submitted record according to existing retention rules.
- **FR-003**: The success popup MUST state that the idea was submitted and provide an acknowledgment action that clearly indicates it starts a fresh intake. The current intake MUST NOT reset before acknowledgment.
- **FR-004**: Acknowledgment MUST clear all prior-intake state listed in User Story 1, restore initial progress, and prepare a distinct fresh intake. No declaration, signature, submission date, accepted value, or pending old result may carry forward; reset MUST NOT delete the submitted record.
- **FR-005**: An unsuccessful or uncertain submission MUST retain the draft, explain the failure or uncertainty, and permit safe recovery without displaying success or resetting. Repeated activation, retry, or repeated delivery MUST NOT create duplicate submissions or confirmations.
- **FR-006**: If fresh-intake preparation fails after confirmed submission, the system MUST identify this as a fresh-start failure, offer fresh-start retry, and prevent edits or resubmission of the submitted intake.
- **FR-007**: Every NoFacts rejection produced while processing chat, supported documents, or supported audio MUST result in a nonmodal security denial banner for that input operation. Equivalent operations through existing interaction modes MUST produce equivalent feedback.
- **FR-008**: The denial MUST identify the actual applicable existing rejection categories: unverified numbers, percentages, costs, dates, or word-form quantities. It MUST explain that the affected information was not accepted and invite a correction without unsupported claims. If a detailed reason is unavailable, it MUST explicitly say so without inventing one.
- **FR-009**: NoFacts MUST continue to drop rejected candidate values before persistence or display as extracted facts. Denial feedback MUST contain only safe reason descriptions, never rejected candidate text, source excerpts, personal information, internal diagnostics, or instructions for bypassing the gate. No new retention of rejected content is permitted.
- **FR-010**: Mixed results MUST preserve accepted candidates and prior accepted values while excluding rejected candidates. Feedback MUST distinguish partial exclusion from denial of the entire idea; safety denial MUST NOT reset the intake or weaken any gate.
- **FR-011**: One input operation MUST produce at most one denial banner listing each applicable reason once. Repeated delivery of that operation's result MUST NOT reopen dismissed feedback, while a later rejected operation MUST receive its own feedback.
- **FR-012**: Dismissing a denial MUST preserve the current intake and permit correction. Each banner MUST offer Correct this input, selecting only that operation for the next dispatched chat message or upload; a visible selection MUST offer Cancel correction, and selecting another banner MUST replace it. Dispatch MUST consume the selection once and preserve the link across transport fallback. Only a linked result with at least one accepted field update, no field-validation failure, and explicitly null safety_notice MUST clear the linked earlier banner; errors, empty results, legacy-absent metadata, and mixed/rejected results MUST preserve it. Unlinked operations MUST NOT clear other banners. Dismissal cancels an undispatched selection for that banner; duplicate or old-generation results MUST NOT restore cleared/dismissed notices.
- **FR-013**: Both outcomes MUST have accessible titles, readable text, and labeled actions. Only the confirmation is modal and traps focus; the denial banner MUST announce its alert without stealing focus or preventing editing. Focus and dismissal MUST follow User Story 3, with normal Tab order, no positive tab indices, and all content reachable at 320-pixel width and 200% zoom without horizontal scrolling.
- **FR-014**: Non-safety validation, processing failures, and submission errors MUST remain distinguishable from NoFacts denials and confirmed submission success. Missing required fields MUST be identified without a false success or reset.
- **FR-015**: The feature MUST preserve the canonical 27 fields, 6 sections, 18 mandatory fields, human-only declaration boundaries, one clarification question per turn, in-memory-only source processing, and absence of personal information from logs. Rejection reasons MUST be separate from accepted field values so rejected values remain silently dropped as required by the constitution.
- **FR-016**: Verification MUST cover confirmation, complete reset, all rejection categories and supported input paths, partial acceptance, duplicate and late results, recovery, and accessible operation. Applicable safety and conversation checks MUST be included in the existing golden evaluation coverage, with at least 50 cases and 100% passing with no omissions before merge.
- **FR-017**: Every known NoFacts rejection MUST carry structured denial metadata with status denied, reason NoFacts, and safe category reasons, separately from the intake lifecycle status. Mixed acceptance MUST remain possible and the whole idea MUST NOT be marked denied.
- **FR-018**: All email acceptance and final-readiness checks MUST use the same strict ASCII email policy: unquoted ASCII dot-atom local part of at most 64 characters with no empty dot segments; total address at most 254 characters; domain at most 253 characters containing at least two labels of 1-63 letters, digits, or hyphens, with no leading/trailing hyphen; final label 2-63 ASCII letters or a valid round-tripping xn-- IDNA label. Every xn-- label, not only the final label, MUST decode, validate, and round-trip under strict IDNA2008 without UTS #46 or transitional mappings, comparing ASCII labels case-insensitively. Valid punycode domain labels are accepted; raw Unicode, single-label domains, numeric TLDs, IP literals, and DNS-dependent validation are excluded. Existing stored invalid emails MUST block final submission without deletion or silent replacement.
- **FR-019**: Outcome handling MUST use validated contract types and exhaustive states without unvalidated type assertions, any-typed outcome data, unreachable branches, unhandled asynchronous failures, or success-shaped error fallbacks. Every failure MUST produce safe, distinguishable feedback.
- **FR-020**: Reset MUST affect only the current intake and MUST introduce zero browser-storage writes or serialization loops. Repeated feedback mount/dismiss/reset cycles MUST release owned dialogs, listeners, timers, connections, and any owned portal containers, without growing retained resources.
- **FR-021**: All feature unit/component/contract/integration tests, frontend lint/type/build checks, PostgreSQL race/migration checks, and the complete golden evaluation MUST be wired to the installable pre-push verification command and active GitHub Actions gates. Missing required verification dependencies MUST fail the gate rather than silently skip. No executable workflow may be disabled; required GitHub merge checks MUST be verified separately from workflow-file existence.
- **FR-022**: Each functional requirement and measurable outcome MUST map to concrete task IDs, acceptance scenarios, and verification selectors; audit findings MUST have explicit remediation and regression tasks. Pending tasks MUST NOT be represented as verified remediation.

### Key Entities

- **Intake Draft**: The employee's in-progress idea, accepted field values, personally entered declarations, conversation, source selections, clarification, and progress.
- **Submission Outcome**: A confirmed successful, unsuccessful, or uncertain final-submission result associated with one draft; only confirmed success authorizes confirmation and subsequent reset.
- **Safety Rejection Notice**: Safe, deduplicated reason categories associated with one input operation; contains no rejected candidate content and is separate from accepted intake fields.
- **Fresh Intake**: A distinct intake with initial state and no inherited content from the submitted idea.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of final-submission acceptance tests, confirmed success produces exactly one confirmation; incomplete, failed, uncertain, and merely ready drafts produce none.
- **SC-002**: In 100% of reset tests, acknowledgment leaves zero prior-intake field values, declarations, messages, source selections, clarifications, or errors in the fresh intake, and the submitted idea remains retained.
- **SC-003**: In 100% of safety acceptance tests covering every existing NoFacts category across chat and each supported document and audio format, employees receive the corresponding safe reason, with zero rejected values accepted, persisted as field values, or repeated in denial feedback.
- **SC-004**: In 100% of mixed-result and correction tests, accepted information remains available, denial does not reset the draft, and the employee can continue with a valid correction.
- **SC-005**: In 100% of duplicate, delayed-result, and recovery tests, no duplicate idea is submitted and no old result contaminates a fresh intake.
- **SC-006**: Both outcome journeys can be completed using only a keyboard, their titles and messages are available to assistive technology, and all modal/banner content remains reachable at 320-pixel width and 200% zoom in every accessibility acceptance test.
- **SC-007**: Under normal supported interaction conditions, confirmation or denial becomes visible within one second after the corresponding outcome is available, excluding the time required to process or submit the idea.
- **SC-008**: All agreed valid/invalid email fixtures produce the expected result in extraction and final-readiness tests, including punycode, invalid TLD, length, and label boundaries.
- **SC-009**: After 100 feedback mount/dismiss cycles and 10 acknowledged fresh-intake cycles, tests observe zero new browser-storage writes and no retained growth in owned dialog/banner nodes, portal containers, event listeners, timers, or old connections.
- **SC-010**: Both pre-push and GitHub Actions execute every required feature suite and golden case, reject an intentionally failing sentinel check, and reject missing PostgreSQL prerequisites in required mode; no required check is skipped or disabled.

## Assumptions

- The employee confirmed that confirmation and reset are triggered by an explicit final Submit action after mandatory fields and human declarations are complete, not by individual messages, uploads, or automatic field completion.
- Reset follows explicit acknowledgment of confirmed success, allowing the employee to read the outcome before starting another idea.
- A NoFacts rejection concerns candidate information, not the employee's access rights or the legitimacy of the whole idea. Other accepted information is retained.
- NoFacts remains the existing deterministic policy; this feature adds safe explanations, not new rejection rules, overrides, or permission to expose dropped content. Safe category-only notices are separate from the silently discarded values.
- Existing supported sources remain PDF, DOCX, PPTX, WAV, MP3, and WebM. No new source formats, schema changes, authentication changes, or retention policy changes are in scope.
- The existing intake does not currently expose a final submission action; establishing a verifiable final submitted outcome is part of this feature, not an assumption that field completion already means submission.
- Reliable final-submission outcomes, safe reason categories from the existing gate, and preparation of a fresh intake are dependencies of the popup journeys.
- The employee selected a nonmodal denial banner, not a second modal; Escape or Close on success dismisses only the modal and leaves the submitted summary frozen until Start a new idea.
- Email validation is syntactic, uses the agreed ASCII/punycode policy, and does not claim that a domain or mailbox exists.
