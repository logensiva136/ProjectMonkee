// Route: "/account" — your own password, sessions and recovery codes.
// Endpoints: /api/v1/auth/{password/change,sessions,recovery-codes/regenerate}

import { useState } from 'react'
import type { FormEvent } from 'react'
import { toast } from 'sonner'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { StatusDot } from '@/components/ui/StatusDot'
import { RecoveryCodesPanel } from '@/features/setup/RecoveryCodesPanel'
import {
  useChangePassword,
  useRegenerateRecoveryCodes,
  useRevokeSession,
  useSessions,
} from '@/features/auth/api'
import { useSession } from '@/hooks/useSession'
import { ApiError } from '@/lib/api'
import { formatDateTime } from '@/lib/utils'

export function AccountPage() {
  const session = useSession()
  const sessions = useSessions()
  const revoke = useRevokeSession()
  const changePassword = useChangePassword()
  const regenerate = useRegenerateRecoveryCodes()

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [newCodes, setNewCodes] = useState<string[]>([])

  function submitPassword(event: FormEvent) {
    event.preventDefault()
    changePassword.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent('')
          setNext('')
          toast.success('Password changed. Other sessions were signed out.')
          sessions.refetch()
        },
      },
    )
  }

  const passwordError = changePassword.error instanceof ApiError ? changePassword.error : null

  if (newCodes.length > 0) {
    return (
      <div className="mx-auto flex max-w-lg flex-col gap-4 p-4 sm:p-6">
        <PageHeader title="New recovery codes" />
        <Card>
          <RecoveryCodesPanel
            codes={newCodes}
            orgName={session.me?.org_name ?? null}
            onContinue={() => setNewCodes([])}
          />
        </Card>
      </div>
    )
  }

  return (
    <div className="flex max-w-2xl flex-col gap-4 p-4 sm:p-6">
      <PageHeader title="Account" description={session.me?.user.email ?? ''} />

      <Card title="Change password">
        <form onSubmit={submitPassword} className="flex flex-col gap-4">
          {passwordError !== null && (
            <Alert tone="error">
              {passwordError.fieldProblems.length > 0 ? (
                <ul className="list-disc pl-4">
                  {passwordError.fieldProblems.map((problem) => (
                    <li key={problem}>{problem}</li>
                  ))}
                </ul>
              ) : (
                passwordError.message
              )}
            </Alert>
          )}

          <Field label="Current password" required>
            <Input
              type="password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              autoComplete="current-password"
              required
            />
          </Field>

          <Field
            label="New password"
            required
            hint="At least 12 characters, mixing three character classes."
          >
            <Input
              type="password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
              autoComplete="new-password"
              required
            />
          </Field>

          <Alert tone="warning">
            Changing your password signs out every other session, on every device.
          </Alert>

          <div className="flex justify-end">
            <Button type="submit" variant="primary" disabled={changePassword.isPending}>
              {changePassword.isPending ? 'Changing…' : 'Change password'}
            </Button>
          </div>
        </form>
      </Card>

      <Card
        title="Active sessions"
        meta={sessions.data === undefined ? undefined : `${sessions.data.length}`}
      >
        {sessions.isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <ul className="divide-y divide-border">
            {(sessions.data ?? []).map((item) => (
              <li key={item.id} className="flex items-center gap-3 py-2.5">
                <StatusDot status={item.is_current ? 'ok' : 'unknown'} />

                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-text">
                    {item.user_agent ?? 'Unknown device'}
                    {item.is_current && <span className="ml-2 text-xs text-ok">this session</span>}
                  </p>
                  <p className="machine truncate text-xs text-text-dim">
                    {item.ip ?? 'unknown address'} · started {formatDateTime(item.created_at)}
                  </p>
                </div>

                {!item.is_current && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      revoke.mutate(item.id, {
                        onSuccess: () => toast.success('Session revoked.'),
                      })
                    }
                  >
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Recovery codes">
        <div className="flex flex-col gap-3">
          <p className="text-sm text-text-muted">
            Generating new codes invalidates every existing one immediately. Do this if you think
            your saved codes may have been seen.
          </p>
          <div className="flex justify-end">
            <Button
              variant="secondary"
              disabled={regenerate.isPending}
              onClick={() =>
                regenerate.mutate(undefined, {
                  onSuccess: (result) => setNewCodes(result.recovery_codes),
                  onError: (error) =>
                    toast.error(
                      error instanceof ApiError ? error.message : 'Could not regenerate.',
                    ),
                })
              }
            >
              {regenerate.isPending ? 'Generating…' : 'Generate new codes'}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  )
}
