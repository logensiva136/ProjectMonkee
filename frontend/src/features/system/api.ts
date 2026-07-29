// Data hooks for the system status screen.
// Endpoints: GET /api/v1/health, GET /api/v1/ready
//
// One hook per endpoint, named after it, with useQuery written inline
// (SPEC §9.0 Rule 3 — no custom wrappers around TanStack Query).
//
// Types come from the generated schema (SPEC §9.0 Rule 0). The
// `components['schemas']['X']` form is index access into the generated file —
// read it like a dict lookup. Never hand-write one of these.

import { useQuery } from '@tanstack/react-query'

import { apiGet, apiGetTolerating } from '@/lib/api'
import type { components } from '@/types/api.gen'

export type HealthResponse = components['schemas']['HealthResponse']
export type ReadyResponse = components['schemas']['ReadyResponse']
export type DependencyCheck = components['schemas']['DependencyCheck']
export type HeartbeatInfo = components['schemas']['HeartbeatInfo']

/** Liveness: identity and version of the API process. */
export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: () => apiGet('/health'),
  })
}

/** Readiness: Postgres and Redis reachability, plus the last Celery heartbeat. */
export function useReady() {
  return useQuery<ReadyResponse>({
    queryKey: ['ready'],
    // 503 is a meaningful answer here, not a failure — see apiGetTolerating.
    queryFn: () => apiGetTolerating('/ready', [503]),
    // Poll so the heartbeat age on screen stays truthful.
    refetchInterval: 10_000,
    staleTime: 0,
  })
}
