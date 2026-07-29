// Data hooks for the onboarding wizard.
// Endpoints: /api/v1/setup/{password-check,totp,monogram-preview,logo,complete}

import { useMutation } from '@tanstack/react-query'

import { apiPost, apiUpload } from '@/lib/api'
import type { components } from '@/types/api.gen'

export type PasswordCheckResponse = components['schemas']['PasswordCheckResponse']
export type TotpEnrolmentResponse = components['schemas']['TotpEnrolmentResponse']
export type TotpVerifyResponse = components['schemas']['TotpVerifyResponse']
export type MonogramPreviewResponse = components['schemas']['MonogramPreviewResponse']
export type LogoUploadResponse = components['schemas']['LogoUploadResponse']
export type SetupCompleteRequest = components['schemas']['SetupCompleteRequest']
export type SetupCompleteResponse = components['schemas']['SetupCompleteResponse']

/** Live strength meter. Runs the same policy `/setup/complete` enforces. */
export function useCheckPassword() {
  return useMutation<
    PasswordCheckResponse,
    Error,
    { password: string; username?: string; email?: string; full_name?: string }
  >({
    mutationFn: (payload) => apiPost('/setup/password-check', payload),
  })
}

/** Mint a TOTP secret. Nothing is persisted until `/setup/complete`. */
export function useEnrolTotp() {
  return useMutation<TotpEnrolmentResponse, Error, string>({
    mutationFn: (username) =>
      apiPost(`/setup/totp?username=${encodeURIComponent(username || 'operator')}`),
  })
}

/** Step 4's gate. Verifies a code without persisting anything. */
export function useVerifyTotp() {
  return useMutation<TotpVerifyResponse, Error, { secret: string; code: string }>({
    mutationFn: (payload) => apiPost('/setup/verify-totp', payload),
  })
}

export function usePreviewMonogram() {
  return useMutation<MonogramPreviewResponse, Error, string>({
    mutationFn: (name) => apiPost(`/setup/monogram-preview?name=${encodeURIComponent(name)}`),
  })
}

export function useUploadLogo() {
  return useMutation<LogoUploadResponse, Error, File>({
    mutationFn: (file) => {
      const form = new FormData()
      form.append('file', file)
      return apiUpload('/setup/logo', form)
    },
  })
}

/** The single atomic submission that creates the instance. */
export function useCompleteSetup() {
  return useMutation<SetupCompleteResponse, Error, SetupCompleteRequest>({
    mutationFn: (payload) => apiPost('/setup/complete', payload),
  })
}
