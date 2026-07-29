// HTTP client for the HAYABUSA API.
//
// Every request goes to a RELATIVE path (`/api/v1/...`). In production nginx
// proxies that to the api service; in development Vite's dev server proxies it.
// Either way the browser sees one origin, so there is no CORS preflight and the
// SameSite=Strict refresh cookie (SPEC §6.2) is sent normally.
//
// Errors arrive as RFC 7807 problem+json (SPEC §7) and are re-thrown as ApiError.

export const API_BASE = '/api/v1'

/** Shape of an RFC 7807 error body as produced by `app/core/errors.py`. */
export interface Problem {
  type: string
  title: string
  status: number
  detail: string
  instance?: string
  request_id?: string
  errors?: { field: string; message: string; type: string }[]
}

/**
 * An API call that returned a non-2xx status.
 *
 * `requestId` is the value to quote when reading the backend logs — it is the
 * same ID structlog stamps on every line for that request.
 */
export class ApiError extends Error {
  status: number
  problem: Problem | null
  requestId: string | null

  constructor(status: number, problem: Problem | null) {
    super(problem?.detail ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.problem = problem
    this.requestId = problem?.request_id ?? null
  }
}

async function parseProblem(response: Response): Promise<Problem | null> {
  try {
    return (await response.json()) as Problem
  } catch {
    // A proxy error page or a dropped connection is not JSON.
    return null
  }
}

// SPEC §9.0 Rule 2: `any` as the deliberate escape hatch. Typing this generically
// would mean declaring our own type parameter, which Rule 1 bans outright. The
// real type is supplied one level up, at the `useQuery<T>` call in each
// feature's api.ts — which is also where a maintainer looks to see the shape.
type ApiResult = any

async function request(
  method: string,
  path: string,
  body?: unknown,
  extraOkStatuses: number[] = [],
): Promise<ApiResult> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    // Send cookies so the refresh-token cookie reaches /auth/refresh.
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok && !extraOkStatuses.includes(response.status)) {
    throw new ApiError(response.status, await parseProblem(response))
  }

  // 204 No Content has no body to parse.
  if (response.status === 204) return null

  return response.json()
}

export function apiGet(path: string): Promise<ApiResult> {
  return request('GET', path)
}

/**
 * GET a path, accepting some non-2xx statuses as success.
 *
 * `/ready` answers 503 when a dependency is down so a load balancer stops
 * routing to it — but the body is still the full readiness report, which is
 * precisely what the status screen needs to render. Without this the UI would
 * show "request failed" at exactly the moment it has something useful to say.
 */
export function apiGetTolerating(path: string, extraOkStatuses: number[]): Promise<ApiResult> {
  return request('GET', path, undefined, extraOkStatuses)
}

export function apiPost(path: string, body?: unknown): Promise<ApiResult> {
  return request('POST', path, body)
}

export function apiPatch(path: string, body?: unknown): Promise<ApiResult> {
  return request('PATCH', path, body)
}

export function apiDelete(path: string): Promise<ApiResult> {
  return request('DELETE', path)
}
