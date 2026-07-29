// The "add user" form on /admin/users.
// Endpoint: POST /api/v1/users (via useCreateUser)
//
// No second factor is set here. An administrator enrolling someone else's
// authenticator would mean holding their second factor, which defeats having
// one — the new user enrols on first sign-in.

import { useState } from 'react'
import type { FormEvent } from 'react'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { useCreateUser } from '@/features/admin/api'
import type { RoleDetail } from '@/features/admin/api'
import { ApiError } from '@/lib/api'

interface Props {
  roles: RoleDetail[]
  onCreated: () => void
  onCancel: () => void
}

export function CreateUserForm({ roles, onCreated, onCancel }: Props) {
  const create = useCreateUser()

  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [roleKeys, setRoleKeys] = useState<string[]>(['viewer'])

  function toggleRole(key: string) {
    setRoleKeys(
      roleKeys.includes(key) ? roleKeys.filter((item) => item !== key) : [...roleKeys, key],
    )
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      {
        full_name: fullName.trim(),
        username: username.trim().toLowerCase(),
        email: email.trim(),
        password,
        role_keys: roleKeys,
        must_change_password: true,
      },
      { onSuccess: onCreated },
    )
  }

  const error = create.error instanceof ApiError ? create.error : null

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
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

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name" required>
          <Input
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            autoFocus
            required
          />
        </Field>

        <Field label="Username" required>
          <Input
            value={username}
            onChange={(event) => setUsername(event.target.value.toLowerCase())}
            maxLength={32}
            required
          />
        </Field>
      </div>

      <Field label="Email address" required>
        <Input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
      </Field>

      <Field
        label="Initial password"
        required
        hint="They must change it at first sign-in, and enrol two-factor then."
      >
        <Input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          required
        />
      </Field>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium text-text-muted">Roles</legend>
        <div className="flex flex-col gap-1.5">
          {roles.map((role) => (
            <label
              key={role.key}
              className="flex cursor-pointer items-start gap-2.5 text-sm text-text-muted"
            >
              <input
                type="checkbox"
                checked={roleKeys.includes(role.key)}
                onChange={() => toggleRole(role.key)}
                className="mt-0.5 size-4 shrink-0 accent-[rgb(var(--accent))]"
              />
              <span>
                <span className="text-text">{role.name}</span>
                <span className="block text-xs text-text-dim">{role.description}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex justify-end gap-2 border-t border-border pt-4">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={create.isPending}>
          {create.isPending ? 'Creating…' : 'Create user'}
        </Button>
      </div>
    </form>
  )
}
