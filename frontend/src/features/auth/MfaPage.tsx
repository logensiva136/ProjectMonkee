// Route: "/login/mfa" — the second factor.
// Endpoint: POST /api/v1/auth/mfa/verify (via ./api.ts)
//
// Accepts a six-digit TOTP code or a single-use recovery code; the API decides
// which was supplied, so this screen only chooses the input's presentation.

import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { AuthLayout } from '@/features/auth/AuthLayout'
import { useVerifyMfa } from '@/features/auth/api'
import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { ApiError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

export function MfaPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const verify = useVerifyMfa()

  const mfaToken = useAuthStore((state) => state.mfaToken)
  const setAccessToken = useAuthStore((state) => state.setAccessToken)
  const setMfaToken = useAuthStore((state) => state.setMfaToken)

  const [code, setCode] = useState('')
  const [useRecoveryCode, setUseRecoveryCode] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/'

  // Landing here directly — or after the five-minute token expired — means
  // there is nothing to verify against.
  if (mfaToken === null) return <Navigate to="/login" replace />

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    verify.mutate(
      { mfa_token: mfaToken ?? '', code },
      {
        onSuccess: (result) => {
          setAccessToken(result.access_token)
          setMfaToken(null)
          navigate(from, { replace: true })
        },
      },
    )
  }

  const error = verify.error instanceof ApiError ? verify.error : null

  return (
    <AuthLayout
      title="Two-factor authentication"
      subtitle={
        useRecoveryCode
          ? 'Enter one of your saved recovery codes'
          : 'Enter the code from your authenticator app'
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error !== null && <Alert tone="error">{error.message}</Alert>}

        <Field
          label={useRecoveryCode ? 'Recovery code' : 'Authentication code'}
          required
          hint={
            useRecoveryCode
              ? 'Each code works once. Hyphens and capitalisation do not matter.'
              : undefined
          }
        >
          <Input
            mono
            value={code}
            onChange={(event) => setCode(event.target.value)}
            // `one-time-code` lets iOS and Android offer the SMS/authenticator
            // code straight from the keyboard.
            autoComplete="one-time-code"
            inputMode={useRecoveryCode ? 'text' : 'numeric'}
            placeholder={useRecoveryCode ? 'XXXXX-XXXXX' : '000000'}
            maxLength={useRecoveryCode ? 16 : 6}
            autoFocus
            required
            invalid={error !== null}
            className="text-center text-lg"
          />
        </Field>

        <Button type="submit" variant="primary" disabled={verify.isPending}>
          {verify.isPending ? 'Verifying…' : 'Verify'}
        </Button>

        <button
          type="button"
          onClick={() => {
            setUseRecoveryCode(!useRecoveryCode)
            setCode('')
          }}
          className="text-sm text-accent underline underline-offset-4 hover:no-underline"
        >
          {useRecoveryCode
            ? 'Use your authenticator app instead'
            : 'Lost your device? Use a recovery code'}
        </button>
      </form>
    </AuthLayout>
  )
}
