export type IntakeSession = {
  session_id: string;
  status: string;
  schema_version: string;
};

export type IntakeFieldState = {
  field_key: string;
  mandatory: boolean;
  human_only: boolean;
  value?: string;
  origin?: 'ai_extracted' | 'human_entered';
};

export type HumanFieldUpdate = {
  field_key: string;
  value: string;
  origin: 'human_entered';
};

export type IntakeResult = {
  request_id: string;
  field_updates: Array<{ field_key: string; value: string; origin: 'ai_extracted' }>;
  clarification: { field_key: string; question: string } | null;
  status: 'in_progress' | 'submitted';
  safety_notice?: SafetyNotice | null;
};

export type SafetyReason = 'number' | 'percentage' | 'cost' | 'date' | 'word_quantity';

export type SafetyNotice = {
  code: 'NO_FACTS_REJECTED';
  status: 'denied';
  reason: 'NoFacts';
  reasons: SafetyReason[];
};

export type SubmissionReadiness = {
  ready: boolean;
  missing_fields: string[];
  invalid_fields: string[];
};

export type SubmissionReceipt = {
  session_id: string;
  status: 'submitted';
  submitted_at: string;
};

export type SubmissionErrorCode =
  | 'SUBMISSION_INCOMPLETE'
  | 'SUBMISSION_CLOSED'
  | 'SERVICE_UNAVAILABLE'
  | 'REQUEST_INVALID'
  | 'SOURCE_INVALID'
  | 'SOURCE_PROCESSING_UNAVAILABLE'
  | 'SOURCE_TOO_LARGE'
  | 'SOURCE_UNSUPPORTED'
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'SESSION_NOT_FOUND';

export class IntakeServiceError extends Error {
  constructor(
    message: string,
    readonly code: SubmissionErrorCode,
    readonly status: number,
    readonly missing_fields: string[] = [],
    readonly invalid_fields: string[] = [],
  ) {
    super(message);
    this.name = 'IntakeServiceError';
  }
}

export class IntakeProtocolError extends Error {
  constructor() {
    super('The server returned an invalid response.');
    this.name = 'IntakeProtocolError';
  }
}

export class IntakeTransportError extends Error {
  constructor() {
    super('The message transport could not be completed.');
    this.name = 'IntakeTransportError';
  }
}

type FieldResponse = {
  session_id: string;
  schema_version: string;
  sections: Array<{ section_key: string; fields: IntakeFieldState[] }>;
  status: 'in_progress' | 'submitted';
  submitted_at: string | null;
  readiness: SubmissionReadiness;
};

const safetyReasons: SafetyReason[] = ['number', 'percentage', 'cost', 'date', 'word_quantity'];
const serviceMessages: Record<SubmissionErrorCode, string> = {
  SUBMISSION_INCOMPLETE: 'Complete the required information and save your declaration before submitting.',
  SUBMISSION_CLOSED: 'This idea has already been submitted.',
  SERVICE_UNAVAILABLE: 'The intake service is temporarily unavailable.',
  REQUEST_INVALID: 'The request could not be processed.',
  SOURCE_INVALID: 'This source could not be processed.',
  SOURCE_PROCESSING_UNAVAILABLE: 'This source could not be processed.',
  SOURCE_TOO_LARGE: 'This source exceeds the allowed size.',
  SOURCE_UNSUPPORTED: 'This source could not be processed.',
  UNAUTHENTICATED: 'Authentication is required.',
  FORBIDDEN: 'This request is not allowed.',
  SESSION_NOT_FOUND: 'Session not found.',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isSafetyReason(value: unknown): value is SafetyReason {
  return safetyReasons.some((reason) => reason === value);
}

function isSubmissionErrorCode(value: string): value is SubmissionErrorCode {
  return value === 'SUBMISSION_INCOMPLETE' || value === 'SUBMISSION_CLOSED' || value === 'SERVICE_UNAVAILABLE';
}

function isKnownServiceErrorCode(value: string): value is SubmissionErrorCode {
  return Object.prototype.hasOwnProperty.call(serviceMessages, value);
}

function protocolError(): never {
  throw new IntakeProtocolError();
}

function decodeFieldKeys(value: unknown): string[] {
  if (
    !Array.isArray(value) ||
    !value.every((field): field is string => typeof field === 'string' && /^[a-z][a-z0-9_]*$/.test(field))
  ) {
    return protocolError();
  }
  return [...new Set(value)];
}

export function decodeSafetyNotice(value: unknown): SafetyNotice | null {
  if (value === null) return null;
  if (
    !isRecord(value) ||
    value.code !== 'NO_FACTS_REJECTED' ||
    value.status !== 'denied' ||
    value.reason !== 'NoFacts' ||
    !Array.isArray(value.reasons) ||
    !value.reasons.every(isSafetyReason)
  ) {
    return protocolError();
  }
  const reasons = value.reasons;
  if (new Set(reasons).size !== reasons.length) return protocolError();
  const ordered = safetyReasons.filter((reason) => reasons.includes(reason));
  if (ordered.some((reason, index) => reasons[index] !== reason)) return protocolError();
  return { code: 'NO_FACTS_REJECTED', status: 'denied', reason: 'NoFacts', reasons: ordered };
}

export function decodeSubmissionReceipt(value: unknown): SubmissionReceipt {
  if (
    !isRecord(value) ||
    typeof value.session_id !== 'string' ||
    !value.session_id ||
    value.status !== 'submitted' ||
    typeof value.submitted_at !== 'string' ||
    Number.isNaN(Date.parse(value.submitted_at))
  ) {
    return protocolError();
  }
  return {
    session_id: value.session_id,
    status: 'submitted',
    submitted_at: value.submitted_at,
  };
}

export function decodeSubmissionError(value: unknown, status: number): IntakeServiceError {
  if (!isRecord(value) || !isRecord(value.error)) return protocolError();
  const { code, missing_fields, invalid_fields } = value.error;
  if (code === 'SUBMISSION_INCOMPLETE') {
    return new IntakeServiceError(
      'Complete the required information and save your declaration before submitting.',
      code,
      status,
      decodeFieldKeys(missing_fields),
      decodeFieldKeys(invalid_fields),
    );
  }
  if (code === 'SUBMISSION_CLOSED') {
    return new IntakeServiceError(serviceMessages[code], code, status);
  }
  if (code === 'SERVICE_UNAVAILABLE') {
    return new IntakeServiceError(serviceMessages[code], code, status);
  }
  return protocolError();
}

function decodeServiceError(value: unknown, status: number): IntakeServiceError {
  if (!isRecord(value) || !isRecord(value.error) || typeof value.error.code !== 'string') {
    return protocolError();
  }
  if (value.error.code === 'SUBMISSION_INCOMPLETE' || value.error.code === 'SUBMISSION_CLOSED' || value.error.code === 'SERVICE_UNAVAILABLE') {
    return decodeSubmissionError(value, status);
  }
  if (isKnownServiceErrorCode(value.error.code)) {
    const code = value.error.code;
    return new IntakeServiceError(serviceMessages[code], code, status);
  }
  return protocolError();
}

function decodeSession(value: unknown): IntakeSession {
  if (
    !isRecord(value) ||
    typeof value.session_id !== 'string' ||
    !value.session_id ||
    (value.status !== 'in_progress' && value.status !== 'submitted') ||
    typeof value.schema_version !== 'string'
  ) {
    return protocolError();
  }
  return {
    session_id: value.session_id,
    status: value.status,
    schema_version: value.schema_version,
  };
}

function decodeFieldState(value: unknown): FieldResponse {
  if (
    !isRecord(value) ||
    typeof value.session_id !== 'string' ||
    typeof value.schema_version !== 'string' ||
    (value.status !== 'in_progress' && value.status !== 'submitted') ||
    !(value.submitted_at === null || typeof value.submitted_at === 'string') ||
    !isRecord(value.readiness) ||
    typeof value.readiness.ready !== 'boolean' ||
    !Array.isArray(value.sections)
  ) {
    return protocolError();
  }
  const sections: FieldResponse['sections'] = [];
  for (const section of value.sections) {
    if (!isRecord(section) || typeof section.section_key !== 'string' || !Array.isArray(section.fields)) {
      return protocolError();
    }
    const fields: IntakeFieldState[] = [];
    for (const field of section.fields) {
      if (
        !isRecord(field) ||
        typeof field.field_key !== 'string' ||
        typeof field.mandatory !== 'boolean' ||
        typeof field.human_only !== 'boolean' ||
        !(field.value === undefined || typeof field.value === 'string') ||
        !(field.origin === undefined || field.origin === 'ai_extracted' || field.origin === 'human_entered')
      ) {
        return protocolError();
      }
      fields.push({
        field_key: field.field_key,
        mandatory: field.mandatory,
        human_only: field.human_only,
        ...(typeof field.value === 'string' ? { value: field.value } : {}),
        ...(field.origin === 'ai_extracted' || field.origin === 'human_entered' ? { origin: field.origin } : {}),
      });
    }
    sections.push({ section_key: section.section_key, fields });
  }
  return {
    session_id: value.session_id,
    schema_version: value.schema_version,
    status: value.status,
    submitted_at: value.submitted_at,
    readiness: {
      ready: value.readiness.ready,
      missing_fields: decodeFieldKeys(value.readiness.missing_fields),
      invalid_fields: decodeFieldKeys(value.readiness.invalid_fields),
    },
    sections,
  };
}

function decodeHumanFieldUpdate(value: unknown): HumanFieldUpdate {
  if (
    !isRecord(value) ||
    typeof value.field_key !== 'string' ||
    typeof value.value !== 'string' ||
    value.origin !== 'human_entered'
  ) {
    return protocolError();
  }
  return { field_key: value.field_key, value: value.value, origin: 'human_entered' };
}

function decodeAiFieldUpdate(value: unknown): IntakeResult['field_updates'][number] {
  if (
    !isRecord(value) ||
    typeof value.field_key !== 'string' ||
    typeof value.value !== 'string' ||
    value.origin !== 'ai_extracted'
  ) {
    return protocolError();
  }
  return { field_key: value.field_key, value: value.value, origin: 'ai_extracted' };
}

function decodeIntakeResult(value: unknown): IntakeResult {
  if (
    !isRecord(value) ||
    typeof value.request_id !== 'string' ||
    !Array.isArray(value.field_updates) ||
    (value.status !== 'in_progress' && value.status !== 'submitted')
  ) {
    return protocolError();
  }
  const updates = value.field_updates.map(decodeAiFieldUpdate);
  let clarification: IntakeResult['clarification'];
  if (value.clarification === null) {
    clarification = null;
  } else if (
    isRecord(value.clarification) &&
    typeof value.clarification.field_key === 'string' &&
    typeof value.clarification.question === 'string'
  ) {
    clarification = { field_key: value.clarification.field_key, question: value.clarification.question };
  } else {
    return protocolError();
  }
  const result: IntakeResult = {
    request_id: value.request_id,
    field_updates: updates,
    clarification,
    status: value.status,
  };
  if (Object.prototype.hasOwnProperty.call(value, 'safety_notice')) {
    result.safety_notice = decodeSafetyNotice(value.safety_notice);
  }
  return result;
}

type FetchOptions = Parameters<typeof fetch>[1];

const apiOrigin = import.meta.env.VITE_API_ORIGIN ?? '';

async function request<T>(path: string, decode: (value: unknown) => T, init?: FetchOptions): Promise<T> {
  const response = await fetch(`${apiOrigin}${path}`, {
    ...init,
    credentials: 'include',
    headers: { ...(init?.headers ?? {}) },
  });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return protocolError();
  }
  if (!response.ok) throw decodeServiceError(body, response.status);
  return decode(body);
}

export function createSession(): Promise<IntakeSession> {
  return request('/api/v1/sessions', decodeSession, { method: 'POST' });
}

export function getFieldState(sessionId: string): Promise<FieldResponse> {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/fields`, decodeFieldState);
}

export function submitSession(sessionId: string): Promise<SubmissionReceipt> {
  return request(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/submit`,
    decodeSubmissionReceipt,
    { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({}) },
  );
}

export function saveHumanField(
  sessionId: string,
  fieldKey: string,
  value: string | boolean,
): Promise<HumanFieldUpdate> {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/fields/${encodeURIComponent(fieldKey)}`, decodeHumanFieldUpdate, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ value }),
  });
}

export function sendMessage(
  sessionId: string,
  text: string,
  requestId = crypto.randomUUID(),
): Promise<IntakeResult> {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`, decodeIntakeResult, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ request_id: requestId, text }),
  });
}

function sourceType(file: File): string {
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (extension && ['pdf', 'docx', 'pptx', 'wav', 'mp3', 'webm'].includes(extension)) return extension;
  const mimeTypes: Record<string, string> = {
    'application/pdf': 'pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
    'audio/wav': 'wav',
    'audio/mpeg': 'mp3',
    'audio/webm': 'webm',
  };
  return mimeTypes[file.type] ?? '';
}

export function isSupportedSource(file: File): boolean {
  return sourceType(file) !== '';
}

export function uploadSource(
  sessionId: string,
  file: File,
  requestId = crypto.randomUUID(),
): Promise<IntakeResult> {
  const type = sourceType(file);
  if (!type) return Promise.reject(new Error('Unsupported source.'));
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/sources/${type}`, decodeIntakeResult, {
    method: 'POST',
    headers: {
      'content-type': file.type || 'application/octet-stream',
      'x-source-name': file.name,
      'x-request-id': requestId,
    },
    body: file,
  });
}

export function connectIntakeSocket(sessionId: string): Promise<{
  sendMessage: (text: string, requestId?: string) => Promise<IntakeResult>;
  close: () => void;
} | null> {
  const origin = apiOrigin || window.location.origin;
  const socketUrl = new URL(`/api/v1/sessions/${encodeURIComponent(sessionId)}/stream`, origin);
  socketUrl.protocol = socketUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  return new Promise((resolve) => {
    let socket: WebSocket;
    try {
      socket = new WebSocket(socketUrl, 'aimplify.intake.v1');
    } catch {
      resolve(null);
      return;
    }
    const timeout = window.setTimeout(() => {
      socket.close();
      resolve(null);
    }, 1200);
    socket.addEventListener('open', () => {
      window.clearTimeout(timeout);
      resolve({
        sendMessage: (text, selectedRequestId) => new Promise((complete, fail) => {
          const requestId = selectedRequestId ?? crypto.randomUUID();
          const updates: IntakeResult['field_updates'] = [];
          let clarification: IntakeResult['clarification'] = null;
          let timeout: number;
          const cleanup = () => {
            window.clearTimeout(timeout);
            socket.removeEventListener('message', onEvent);
            socket.removeEventListener('close', onClose);
          };
          const failRequest = (error: Error = new IntakeTransportError()) => {
            cleanup();
            fail(error);
          };
          const onEvent = (event: MessageEvent<string>) => {
            let data: unknown;
            try {
              data = JSON.parse(event.data);
            } catch {
              failRequest(new IntakeProtocolError());
              return;
            }
            if (!isRecord(data) || typeof data.type !== 'string' || typeof data.request_id !== 'string') {
              failRequest(new IntakeProtocolError());
              return;
            }
            if (data.request_id !== requestId) return;
            if (data.type === 'server.field.updated') {
              try {
                updates.push(decodeAiFieldUpdate(data.payload));
              } catch {
                failRequest(new IntakeProtocolError());
                return;
              }
            }
            if (data.type === 'server.clarification') {
              const payload = data.payload;
              if (!isRecord(payload) || typeof payload.field_key !== 'string' || typeof payload.question !== 'string') {
                failRequest(new IntakeProtocolError());
                return;
              }
              clarification = { field_key: payload.field_key, question: payload.question };
            }
            if (data.type === 'server.error') {
              const payload = data.payload;
              if (!isRecord(payload) || typeof payload.code !== 'string') {
                failRequest(new IntakeProtocolError());
                return;
              }
              if (isSubmissionErrorCode(payload.code)) {
                const status = payload.code === 'SUBMISSION_CLOSED' ? 409 : payload.code === 'SUBMISSION_INCOMPLETE' ? 422 : 503;
                failRequest(decodeSubmissionError({ error: payload }, status));
              } else if (isKnownServiceErrorCode(payload.code)) {
                const status = payload.code === 'SOURCE_TOO_LARGE' ? 413 : payload.code === 'SOURCE_INVALID' ? 400 : 503;
                failRequest(new IntakeServiceError(serviceMessages[payload.code], payload.code, status));
              } else {
                failRequest(new IntakeProtocolError());
              }
            }
            if (data.type === 'server.submission.status') {
              const payload = data.payload;
              if (!isRecord(payload) || (payload.status !== 'in_progress' && payload.status !== 'submitted')) {
                failRequest(new IntakeProtocolError());
                return;
              }
              try {
                const result: IntakeResult = {
                  request_id: requestId,
                  field_updates: updates,
                  clarification,
                  status: payload.status,
                };
                if (Object.prototype.hasOwnProperty.call(payload, 'safety_notice')) {
                  result.safety_notice = decodeSafetyNotice(payload.safety_notice);
                }
                cleanup();
                complete(result);
              } catch {
                failRequest(new IntakeProtocolError());
              }
            }
          };
          const onClose = () => failRequest();
          timeout = window.setTimeout(failRequest, 15000);
          socket.addEventListener('message', onEvent);
          socket.addEventListener('close', onClose, { once: true });
          socket.send(JSON.stringify({ type: 'client.message', request_id: requestId, payload: { text } }));
        }),
        close: () => socket.close(),
      });
    });
    socket.addEventListener('error', () => {
      window.clearTimeout(timeout);
      socket.close();
      resolve(null);
    }, { once: true });
  });
}