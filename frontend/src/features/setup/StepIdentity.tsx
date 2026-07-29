// Wizard step 1: who the first operator is. Calls no API — state is held by
// SetupWizard until the single atomic submit.

import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'

interface Props {
  fullName: string
  username: string
  email: string
  onChange: (field: 'fullName' | 'username' | 'email', value: string) => void
}

/** Mirrors the backend's `^[a-z0-9._-]+$` so the two cannot disagree. */
const USERNAME_ALLOWED = /^[a-z0-9._-]*$/

export function StepIdentity({ fullName, username, email, onChange }: Props) {
  const usernameError =
    username.length > 0 && username.length < 3
      ? 'Use at least 3 characters.'
      : !USERNAME_ALLOWED.test(username)
        ? 'Only lowercase letters, digits, dots, hyphens and underscores.'
        : null

  return (
    <div className="flex flex-col gap-4">
      <Field label="Full name" required>
        <Input
          value={fullName}
          onChange={(event) => onChange('fullName', event.target.value)}
          autoComplete="name"
          autoFocus
          required
        />
      </Field>

      <Field
        label="Username"
        required
        error={usernameError}
        hint="3–32 characters. This is what you sign in with."
      >
        <Input
          value={username}
          // Lowercased as it is typed: the backend stores it lowercase anyway
          // (the column is citext), so showing anything else would be a lie.
          onChange={(event) => onChange('username', event.target.value.toLowerCase())}
          autoComplete="username"
          maxLength={32}
          required
          invalid={usernameError !== null}
        />
      </Field>

      <Field label="Email address" required hint="Used for account recovery and notices.">
        <Input
          type="email"
          value={email}
          onChange={(event) => onChange('email', event.target.value)}
          autoComplete="email"
          required
        />
      </Field>
    </div>
  )
}
