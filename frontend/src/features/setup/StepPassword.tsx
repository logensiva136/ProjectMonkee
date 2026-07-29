// Wizard step 3: choose a password.
// Endpoint: POST /api/v1/setup/password-check (debounced, via useCheckPassword)

import { useEffect } from 'react'

import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { PasswordStrengthMeter } from '@/features/setup/PasswordStrengthMeter'
import { useCheckPassword } from '@/features/setup/api'

interface Props {
  password: string
  confirm: string
  username: string
  email: string
  fullName: string
  onChange: (field: 'password' | 'confirm', value: string) => void
  /** Lets the wizard enable "Continue" only for an acceptable password. */
  onAcceptableChange: (acceptable: boolean) => void
}

export function StepPassword({
  password,
  confirm,
  username,
  email,
  fullName,
  onChange,
  onAcceptableChange,
}: Props) {
  const check = useCheckPassword()

  // Debounce the strength check: 300ms after typing stops. Each keystroke would
  // otherwise run zxcvbn on the server. The cleanup cancels the pending timer
  // whenever the password changes again.
  const mutate = check.mutate
  const reset = check.reset
  useEffect(() => {
    if (password.length === 0) {
      reset()
      onAcceptableChange(false)
      return
    }

    const timer = setTimeout(() => {
      mutate(
        { password, username, email, full_name: fullName },
        { onSuccess: (result) => onAcceptableChange(result.acceptable) },
      )
    }, 300)

    return () => clearTimeout(timer)
  }, [password, username, email, fullName, mutate, reset, onAcceptableChange])

  const mismatch = confirm.length > 0 && confirm !== password

  return (
    <div className="flex flex-col gap-4">
      <Field
        label="Password"
        required
        hint="At least 12 characters, mixing three of: lowercase, uppercase, digits, symbols."
      >
        <Input
          type="password"
          value={password}
          onChange={(event) => onChange('password', event.target.value)}
          autoComplete="new-password"
          autoFocus
          required
        />
      </Field>

      <PasswordStrengthMeter
        result={check.data}
        isChecking={check.isPending}
        hasInput={password.length > 0}
      />

      <Field
        label="Confirm password"
        required
        error={mismatch ? 'The two passwords do not match.' : null}
      >
        <Input
          type="password"
          value={confirm}
          onChange={(event) => onChange('confirm', event.target.value)}
          autoComplete="new-password"
          required
          invalid={mismatch}
        />
      </Field>
    </div>
  )
}
