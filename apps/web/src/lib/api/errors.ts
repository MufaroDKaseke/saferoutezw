/** An HTTP or network failure when talking to the FastAPI backend. */
export class ApiError extends Error {
  readonly status: number | null;
  readonly detail: string | null;
  /** Machine-readable code from the API's error envelope, e.g. STALE_BULLETIN_VERSION. */
  readonly code: string | null;
  /** The request field the API objected to, if it named one. */
  readonly field: string | null;

  constructor(
    message: string,
    status: number | null = null,
    detail: string | null = null,
    code: string | null = null,
    field: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
    this.field = field;
  }
}

/**
 * Raised in `api` mode for data the backend cannot serve yet. The UI shows a
 * "not available yet" state instead of inventing data. Nothing is called.
 */
export class EndpointNotAvailableError extends Error {
  readonly endpoint: string;

  constructor(endpoint: string) {
    super(`The backend does not provide ${endpoint} yet.`);
    this.name = "EndpointNotAvailableError";
    this.endpoint = endpoint;
  }
}

/** Input that failed validation (for example, a rejection without a reason). */
export class ValidationError extends Error {
  readonly field: string | null;

  constructor(message: string, field: string | null = null) {
    super(message);
    this.name = "ValidationError";
    this.field = field;
  }
}

/** The signed-in role may not perform this action. Enforced server-side in api mode. */
export class PermissionError extends Error {
  constructor(message = "Your role cannot record editorial decisions.") {
    super(message);
    this.name = "PermissionError";
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

/** The requested record does not exist. */
export class NotFoundError extends Error {
  constructor(what = "Record") {
    super(`${what} not found.`);
    this.name = "NotFoundError";
  }
}
