// Route: "/login" — the password step.
// Endpoint: POST /api/v1/auth/login (via ./api.ts)
//
// On success the API either signs the user in outright or, for any account with
// 2FA enabled, hands back a five-minute mfa_token and sends them to /login/mfa.

import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { AuthLayout } from '@/features/auth/AuthLayout'
import { useLogin } from '@/features/auth/api'
import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { useSession } from '@/hooks/useSession'
import { ApiError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const session = useSession()
  const login = useLogin()

  const setAccessToken = useAuthStore((state) => state.setAccessToken)
  const setMfaToken = useAuthStore((state) => state.setMfaToken)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  // Where the guard bounced them from, so they land back there after signing in.
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  if (session.needsSetup) return <Navigate to="/setup" replace />
  if (session.isAuthenticated) return <Navigate to={from} replace />

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    login.mutate(
      { username, password },
      {
        onSuccess: (result) => {
          if (result.status === 'mfa_required') {
            setMfaToken(result.mfa_token ?? null)
            navigate('/login/mfa', { state: { from } })
            return
          }
          setAccessToken(result.access_token ?? null)
          navigate(from, { replace: true })
        },
      },
    )
  }

  const error = login.error instanceof ApiError ? login.error : null

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Threat & attack surface monitoring"
      footer={
        error?.requestId !== null && error?.requestId !== undefined ? (
          <span className="machine text-text-dim">ref {error.requestId}</span>
        ) : undefined
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error !== null && (
          <Alert tone={error.status === 429 ? 'warning' : 'error'}>{error.message}</Alert>
        )}

        <Field label="Username" required>
          <Input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoFocus
            required
            invalid={error?.status === 401}
          />
        </Field>

        <Field label="Password" required>
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
            invalid={error?.status === 401}
          />
        </Field>

        <Button type="submit" variant="primary" disabled={login.isPending} className="mt-1">
          {login.isPending ? 'Signing in…' : 'Continue'}
        </Button>
      </form>
    </AuthLayout>
  )
}
