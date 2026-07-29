// Wizard step 4: enrol an authenticator. Mandatory (SPEC §6.1).
// Endpoints: POST /api/v1/setup/totp, POST /api/v1/setup/verify-totp
//
// The secret is minted on the server and held in the wizard's state; nothing is
// persisted until the final submit, so an abandoned wizard leaves no
// half-enrolled account behind.

import { useEffect, useState } from 'react'
import { Check, Copy } from 'lucide-react'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { Skeleton } from '@/components/ui/Skeleton'
import { useEnrolTotp, useVerifyTotp } from '@/features/setup/api'

interface Props {
  username: string
  secret: string
  qrSvg: string
  code: string
  verified: boolean
  onEnrolled: (secret: string, qrSvg: string) => void
  onChange: (code: string) => void
  onVerified: (verified: boolean) => void
}

export function StepTwoFactor({
  username,
  secret,
  qrSvg,
  code,
  verified,
  onEnrolled,
  onChange,
  onVerified,
}: Props) {
  const enrol = useEnrolTotp()
  const verify = useVerifyTotp()
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Mint a secret once, on first arrival at this step. Re-minting on re-entry
  // would invalidate a QR the user may already have scanned.
  const mutate = enrol.mutate
  useEffect(() => {
    if (secret !== '') return
    mutate(username, { onSuccess: (result) => onEnrolled(result.secret, result.qr_svg) })
  }, [secret, username, mutate, onEnrolled])

  function handleVerify() {
    setError(null)
    verify.mutate(
      { secret, code },
      {
        onSuccess: (result) => {
          onVerified(result.valid)
          if (!result.valid) setError(result.detail ?? 'That code is not valid.')
        },
      },
    )
  }

  async function copySecret() {
    await navigator.clipboard.writeText(secret)
    setCopied(true)
    // Revert the confirmation after two seconds; the cleanup prevents the timer
    // firing after the component has gone.
    setTimeout(() => setCopied(false), 2000)
  }

  if (enrol.isPending || secret === '') {
    return <Skeleton className="h-64 w-full" />
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">
        Scan this with Google Authenticator, 1Password, Authy or similar, then enter the code it
        shows. Two-factor authentication is required and cannot be skipped.
      </p>

      <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
        {/* Server-generated SVG from a fixed template — no user input reaches it. */}
        <div
          className="size-40 shrink-0 rounded-md bg-white p-2 [&>svg]:size-full"
          dangerouslySetInnerHTML={{ __html: qrSvg }}
        />

        <div className="flex w-full flex-col gap-3">
          <Field
            label="Or enter this key manually"
            hint="Keep it secret; it is your second factor."
          >
            <div className="flex gap-2">
              <Input readOnly mono value={secret} className="text-xs" />
              <Button type="button" variant="secondary" size="md" onClick={copySecret}>
                {copied ? <Check className="size-4 text-ok" /> : <Copy className="size-4" />}
              </Button>
            </div>
          </Field>

          <Field label="Verification code" required error={error}>
            <div className="flex gap-2">
              <Input
                mono
                value={code}
                onChange={(event) => {
                  onChange(event.target.value.replace(/\D/g, '').slice(0, 6))
                  onVerified(false)
                  setError(null)
                }}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                maxLength={6}
                className="text-center text-lg"
                invalid={error !== null}
              />
              <Button
                type="button"
                variant={verified ? 'secondary' : 'primary'}
                onClick={handleVerify}
                disabled={code.length !== 6 || verify.isPending}
              >
                {verified ? <Check className="size-4 text-ok" /> : 'Verify'}
              </Button>
            </div>
          </Field>
        </div>
      </div>

      {verified && (
        <Alert tone="success" title="Authenticator confirmed">
          You will be shown ten single-use recovery codes after setup completes. Save them then —
          they are not recoverable afterwards.
        </Alert>
      )}
    </div>
  )
}
