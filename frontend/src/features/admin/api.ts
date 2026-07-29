// Data hooks for the administration screens.
// Endpoints: /api/v1/{users,roles,permissions,panels,audit-logs,settings}
//
// One hook per endpoint, named after it, useQuery/useMutation inline
// (SPEC §9.0 Rule 3).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api'
import type { components } from '@/types/api.gen'

export type UserSummary = components['schemas']['UserSummary']
export type UserCreate = components['schemas']['UserCreate']
export type UserUpdate = components['schemas']['UserUpdate']
export type RoleDetail = components['schemas']['RoleDetail']
export type RoleCreate = components['schemas']['RoleCreate']
export type RoleUpdate = components['schemas']['RoleUpdate']
export type PermissionOut = components['schemas']['PermissionOut']
export type PanelOut = components['schemas']['PanelOut']
export type AuditLogOut = components['schemas']['AuditLogOut']
export type AppSettingOut = components['schemas']['AppSettingOut']
export type AppSettingUpdate = components['schemas']['AppSettingUpdate']
export type AuditPage = components['schemas']['CursorPage_AuditLogOut_']

// --------------------------------------------------------------------- users

export function useUsers() {
  return useQuery<UserSummary[]>({
    queryKey: ['users'],
    queryFn: () => apiGet('/users'),
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation<UserSummary, Error, UserCreate>({
    mutationFn: (payload) => apiPost('/users', payload),
    // The list is stale the moment this succeeds; without invalidation the new
    // user does not appear until a reload.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation<UserSummary, Error, { id: string; body: UserUpdate }>({
    mutationFn: ({ id, body }) => apiPatch(`/users/${id}`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useDeleteUser() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (id) => apiDelete(`/users/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useUnlockUser() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (id) => apiPost(`/users/${id}/unlock`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useResetTwoFactor() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (id) => apiPost(`/users/${id}/2fa/reset`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useResetUserPassword() {
  const queryClient = useQueryClient()
  return useMutation<
    unknown,
    Error,
    { id: string; new_password: string; must_change_password: boolean }
  >({
    mutationFn: ({ id, ...body }) => apiPost(`/users/${id}/password`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })
}

// --------------------------------------------------------------------- roles

export function useRoles() {
  return useQuery<RoleDetail[]>({
    queryKey: ['roles'],
    queryFn: () => apiGet('/roles'),
  })
}

export function usePermissions() {
  return useQuery<PermissionOut[]>({
    queryKey: ['permissions'],
    queryFn: () => apiGet('/permissions'),
    // Seeded from code and only changes on deploy.
    staleTime: Infinity,
  })
}

export function useAllPanels() {
  return useQuery<PanelOut[]>({
    queryKey: ['panels'],
    queryFn: () => apiGet('/panels'),
    staleTime: Infinity,
  })
}

export function useCreateRole() {
  const queryClient = useQueryClient()
  return useMutation<RoleDetail, Error, RoleCreate>({
    mutationFn: (payload) => apiPost('/roles', payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['roles'] }),
  })
}

export function useUpdateRole() {
  const queryClient = useQueryClient()
  return useMutation<RoleDetail, Error, { id: string; body: RoleUpdate }>({
    mutationFn: ({ id, body }) => apiPatch(`/roles/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      // Panel changes alter the caller's own sidebar, so /me must refetch too.
      queryClient.invalidateQueries({ queryKey: ['me'] })
    },
  })
}

export function useDeleteRole() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (id) => apiDelete(`/roles/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['roles'] }),
  })
}

// --------------------------------------------------------------------- audit

export function useAuditLogs(filters: { action?: string; entity_type?: string }) {
  const params = new URLSearchParams()
  if (filters.action !== undefined && filters.action !== '') params.set('action', filters.action)
  if (filters.entity_type !== undefined && filters.entity_type !== '') {
    params.set('entity_type', filters.entity_type)
  }
  params.set('limit', '100')

  return useQuery<AuditPage>({
    // The filters belong in the key: two different filters are two different
    // cached results, and omitting them would serve one for the other.
    queryKey: ['audit-logs', filters],
    queryFn: () => apiGet(`/audit-logs?${params.toString()}`),
  })
}

// ------------------------------------------------------------------ settings

export function useSettings() {
  return useQuery<AppSettingOut>({
    queryKey: ['settings'],
    queryFn: () => apiGet('/settings'),
  })
}

export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation<AppSettingOut, Error, AppSettingUpdate>({
    mutationFn: (payload) => apiPatch('/settings', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      queryClient.invalidateQueries({ queryKey: ['me'] })
    },
  })
}
