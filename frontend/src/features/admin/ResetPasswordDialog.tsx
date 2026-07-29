// Set a new password for another user, from /admin/users.
// Endpoint: POST /api/v1/users/{id}/password (via useResetUserPassword)
//
// Every session of the target user ends when this succeeds — including any an
// attacker holds, which is the point of an administrator resetting a password.

import { useState } from 'react'
import type { FormEvent } from 'react'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { useResetUserPassword } from '@/features/admin/api'
import type { UserSummary } from '@/features/admin/api'
import { ApiError } from '@/lib/api'

interface Props {
  user: UserSummary
  onDone: () => void
  onCancel: () => void
}

export function ResetPasswordDialog({ user, onDone, onCancel }: Props) {
  const reset = useResetUserPassword()
  const [password, setPassword] = useState('')
  const [mustChange, setMustChange] = useState(true)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    reset.mutate(
      { id: user.id, new_password: password, must_change_password: mustChange },
      { onSuccess: onDone },
    )
  }

  const error = reset.error instanceof ApiError ? reset.error : null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
      aria-label={`Set a new password for ${user.username}`}
    >
      <form
        onSubmit={handleSubmit}
        onClick={(event) => event.stopPropagation()}
        className="flex w-full max-w-md flex-col gap-4 rounded-md border border-border bg-surface p-5"
      >
        <div>
          <h2 className="text-base font-medium text-text">Set a new password</h2>
          <p className="machine mt-0.5 text-sm text-text-dim">{user.username}</p>
        </div>

        {error !== null && (
          <Alert tone="error">
            {error.fieldProblems.length > 0 ? (
              <ul className="list-disc pl-4">
                {error.fieldProblems.map((problem) => (
                  <li key={problem}>{problem}</li>
                ))}
              </ul>
            ) : (
              error.message
            )}
          </Alert>
        )}

        <Field
          label="New password"
          required
          hint="At least 12 characters, mixing three character classes."
        >
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            autoFocus
            required
          />
        </Field>

        <label className="flex cursor-pointer items-start gap-2.5 text-sm text-text-muted">
          <input
            type="checkbox"
            checked={mustChange}
            onChange={(event) => setMustChange(event.target.checked)}
            className="mt-0.5 size-4 shrink-0 accent-[rgb(var(--accent))]"
          />
          Require them to change it at next sign-in — recommended, since you now know it.
        </label>

        <Alert tone="warning">All of their active sessions will be signed out.</Alert>

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={reset.isPending}>
            {reset.isPending ? 'Setting…' : 'Set password'}
          </Button>
        </div>
      </form>
    </div>
  )
}
