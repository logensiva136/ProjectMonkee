// Data hooks for authentication and the signed-in user.
// Endpoints: /api/v1/auth/*, /api/v1/me, /api/v1/setup/status
//
// One hook per endpoint, useQuery/useMutation written inline (SPEC §9.0 Rule 3).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiDelete, apiGet, apiPost } from '@/lib/api'
import type { components } from '@/types/api.gen'

export type MeResponse = components['schemas']['MeResponse']
export type LoginResponse = components['schemas']['LoginResponse']
export type TokenResponse = components['schemas']['TokenResponse']
export type SetupStatus = components['schemas']['SetupStatus']
export type SessionInfo = components['schemas']['SessionInfo']
export type UserSummary = components['schemas']['UserSummary']
export type PanelOut = components['schemas']['PanelOut']

/** Whether the instance still needs onboarding. Unauthenticated. */
export function useSetupStatus() {
  return useQuery<SetupStatus>({
    queryKey: ['setup-status'],
    queryFn: () => apiGet('/setup/status'),
    // Onboarding happens once and never reverts, so this need not be re-checked.
    staleTime: Infinity,
    retry: false,
  })
}

/** The signed-in user, their permissions and their visible panels. */
export function useMe(enabled: boolean) {
  return useQuery<MeResponse>({
    queryKey: ['me'],
    queryFn: () => apiGet('/me'),
    enabled,
    // Roles can change under the user; a minute is a reasonable staleness bound
    // for navigation, and the backend re-checks permissions on every call anyway.
    staleTime: 60_000,
    retry: false,
  })
}

export function useLogin() {
  return useMutation<LoginResponse, Error, { username: string; password: string }>({
    mutationFn: (credentials) => apiPost('/auth/login', credentials),
  })
}

export function useVerifyMfa() {
  return useMutation<TokenResponse, Error, { mfa_token: string; code: string }>({
    mutationFn: (payload) => apiPost('/auth/mfa/verify', payload),
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, void>({
    mutationFn: () => apiPost('/auth/logout'),
    onSettled: () => {
      // Clear cached server state on the way out, or the next user to sign in
      // on this browser briefly sees the previous user's data.
      queryClient.clear()
    },
  })
}

export function useSessions() {
  return useQuery<SessionInfo[]>({
    queryKey: ['auth', 'sessions'],
    queryFn: () => apiGet('/auth/sessions'),
  })
}

export function useRevokeSession() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (sessionId) => apiDelete(`/auth/sessions/${sessionId}`),
    onSuccess: () => {
      // The list is now stale — tell TanStack Query to refetch it.
      queryClient.invalidateQueries({ queryKey: ['auth', 'sessions'] })
    },
  })
}

export function useChangePassword() {
  return useMutation<unknown, Error, { current_password: string; new_password: string }>({
    mutationFn: (payload) => apiPost('/auth/password/change', payload),
  })
}

export function useRegenerateRecoveryCodes() {
  return useMutation<{ recovery_codes: string[] }, Error, void>({
    mutationFn: () => apiPost('/auth/recovery-codes/regenerate'),
  })
}
