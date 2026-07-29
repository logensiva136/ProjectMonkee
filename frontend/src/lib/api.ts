// HTTP client for the HAYABUSA API.
//
// Every request goes to a RELATIVE path (`/api/v1/...`). In production nginx
// proxies that to the api service; in development Vite's dev server proxies it.
// Either way the browser sees one origin, so there is no CORS preflight and the
// SameSite=Strict refresh cookie (SPEC §6.2) is sent normally.
//
// Errors arrive as RFC 7807 problem+json (SPEC §7) and are re-thrown as ApiError.

import { clearAuth, getAccessToken, setAccessToken } from '@/stores/auth'

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
  problems?: string[]
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

  /** True while the instance has not been onboarded (SPEC §6.1 returns 409). */
  get isSetupRequired(): boolean {
    return this.status === 409 && this.problem?.type.endsWith('/setup-required') === true
  }

  /** Field-level messages for a form, when the API supplied any. */
  get fieldProblems(): string[] {
    return this.problem?.problems ?? this.problem?.errors?.map((e) => e.message) ?? []
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

// --------------------------------------------------------------------------
// Silent refresh
// --------------------------------------------------------------------------

// A single in-flight refresh, shared by every caller.
//
// THIS DEDUPLICATION IS LOAD-BEARING, not an optimisation. The backend rotates
// the refresh token on every use and treats a replayed one as theft, revoking
// the whole family (SPEC §6.2). A dashboard firing six queries at once would
// otherwise send six refreshes; the first rotates the token and the other five
// present the now-revoked one — which looks exactly like an attack and signs
// the user out. One shared promise means one rotation.
let refreshInFlight: Promise<boolean> | null = null

async function performRefresh(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'same-origin',
    })
    if (!response.ok) {
      clearAuth()
      return false
    }
    const body = (await response.json()) as { access_token: string }
    setAccessToken(body.access_token)
    return true
  } catch {
    clearAuth()
    return false
  }
}

export function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight === null) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

// --------------------------------------------------------------------------
// Request
// --------------------------------------------------------------------------

// Endpoints that must never trigger a refresh-and-retry: refreshing in response
// to their 401 would either recurse or paper over a genuine sign-in failure.
const NO_RETRY = ['/auth/refresh', '/auth/login', '/auth/mfa/verify', '/auth/logout']

interface RequestOptions {
  body?: unknown
  /** Non-2xx statuses to treat as success, e.g. `/ready` answering 503. */
  extraOkStatuses?: number[]
  /** Override the bearer token — used for the MFA step. */
  token?: string
  /** Multipart payload. Content-Type is left to the browser so it sets the boundary. */
  formData?: FormData
}

async function send(
  method: string,
  path: string,
  options: RequestOptions,
  isRetry: boolean,
): Promise<Response> {
  const token = options.token ?? getAccessToken()
  const headers: Record<string, string> = {}

  if (token !== null && token !== undefined) headers.Authorization = `Bearer ${token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body:
      options.formData ?? (options.body === undefined ? undefined : JSON.stringify(options.body)),
  })

  // A 401 on a normal call usually means the 15-minute access token expired.
  // Refresh once and replay; `isRetry` stops that becoming a loop.
  if (response.status === 401 && !isRetry && !NO_RETRY.includes(path) && !options.token) {
    if (await refreshAccessToken()) {
      return send(method, path, options, true)
    }
  }

  return response
}

async function request(
  method: string,
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult> {
  const response = await send(method, path, options, false)

  const allowed = options.extraOkStatuses ?? []
  if (!response.ok && !allowed.includes(response.status)) {
    throw new ApiError(response.status, await parseProblem(response))
  }

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
 * precisely what the status screen needs to render.
 */
export function apiGetTolerating(path: string, extraOkStatuses: number[]): Promise<ApiResult> {
  return request('GET', path, { extraOkStatuses })
}

export function apiPost(path: string, body?: unknown, token?: string): Promise<ApiResult> {
  return request('POST', path, { body, token })
}

export function apiPatch(path: string, body?: unknown): Promise<ApiResult> {
  return request('PATCH', path, { body })
}

export function apiDelete(path: string): Promise<ApiResult> {
  return request('DELETE', path)
}

export function apiUpload(path: string, formData: FormData): Promise<ApiResult> {
  return request('POST', path, { formData })
}
