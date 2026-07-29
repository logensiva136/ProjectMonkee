// Route: "/setup" — the first-run onboarding wizard (SPEC §6.1).
// Endpoint: POST /api/v1/setup/complete (plus the per-step helpers in ./api.ts)
//
// All five steps' state lives here and is submitted ONCE, atomically. Nothing
// is written until the final call, so abandoning the wizard leaves no partial
// account behind — which matters because the wizard refuses to run twice.

import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { AuthLayout } from '@/features/auth/AuthLayout'
import { useSetupStatus } from '@/features/auth/api'
import { RecoveryCodesPanel } from '@/features/setup/RecoveryCodesPanel'
import { StepIdentity } from '@/features/setup/StepIdentity'
import { StepOrganisation } from '@/features/setup/StepOrganisation'
import { StepPassword } from '@/features/setup/StepPassword'
import { StepReview } from '@/features/setup/StepReview'
import { StepTwoFactor } from '@/features/setup/StepTwoFactor'
import { Stepper } from '@/features/setup/Stepper'
import { useCompleteSetup } from '@/features/setup/api'
import { ApiError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

const STEPS = ['Identity', 'Organisation', 'Password', 'Two-factor', 'Review']

export function SetupWizard() {
  const navigate = useNavigate()
  const status = useSetupStatus()
  const complete = useCompleteSetup()
  const setAccessToken = useAuthStore((state) => state.setAccessToken)

  const [step, setStep] = useState(0)

  // Step 1
  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  // Step 2
  const [orgName, setOrgName] = useState('')
  const [timezone, setTimezone] = useState('Asia/Kuala_Lumpur')
  const [logoFilename, setLogoFilename] = useState<string | null>(null)
  const [logoUrl, setLogoUrl] = useState<string | null>(null)
  // Step 3
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [passwordAcceptable, setPasswordAcceptable] = useState(false)
  // Step 4
  const [secret, setSecret] = useState('')
  const [qrSvg, setQrSvg] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [totpVerified, setTotpVerified] = useState(false)
  // After submit
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])

  // Already onboarded — the wizard is permanently gone (the API answers 410).
  if (status.data?.needs_setup === false && recoveryCodes.length === 0) {
    return <Navigate to="/login" replace />
  }

  const canAdvance = [
    fullName.trim().length > 0 && username.trim().length >= 3 && email.includes('@'),
    true, // organisation is entirely optional
    passwordAcceptable && password === confirm && confirm.length > 0,
    totpVerified,
    true,
  ][step]

  function submit() {
    complete.mutate(
      {
        full_name: fullName.trim(),
        username: username.trim(),
        email: email.trim(),
        org_name: orgName.trim() || null,
        logo_filename: logoFilename,
        timezone,
        brand_color: '#22D3EE',
        password,
        totp_secret: secret,
        totp_code: totpCode,
        recovery_codes_acknowledged: true,
      },
      {
        onSuccess: (result) => {
          // The response signs us in; the refresh cookie is already set.
          setAccessToken(result.access_token)
          setRecoveryCodes(result.recovery_codes)
        },
      },
    )
  }

  if (recoveryCodes.length > 0) {
    return (
      <AuthLayout title="Save your recovery codes" subtitle="Setup is complete">
        <RecoveryCodesPanel
          codes={recoveryCodes}
          orgName={orgName.trim() || null}
          onContinue={() => navigate('/', { replace: true })}
        />
      </AuthLayout>
    )
  }

  const error = complete.error instanceof ApiError ? complete.error : null

  return (
    <AuthLayout wide title="Set up HAYABUSA" subtitle="This runs once, on first launch">
      <Stepper steps={STEPS} current={step} />

      {error !== null && (
        <Alert tone="error" title="Setup could not complete" className="mb-4">
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

      {step === 0 && (
        <StepIdentity
          fullName={fullName}
          username={username}
          email={email}
          onChange={(field, value) => {
            if (field === 'fullName') setFullName(value)
            else if (field === 'username') setUsername(value)
            else setEmail(value)
          }}
        />
      )}

      {step === 1 && (
        <StepOrganisation
          orgName={orgName}
          timezone={timezone}
          logoFilename={logoFilename}
          logoUrl={logoUrl}
          fallbackName={fullName}
          onChange={(field, value) => {
            if (field === 'orgName') setOrgName(value)
            else setTimezone(value)
          }}
          onLogo={(filename, url) => {
            setLogoFilename(filename)
            setLogoUrl(url)
          }}
        />
      )}

      {step === 2 && (
        <StepPassword
          password={password}
          confirm={confirm}
          username={username}
          email={email}
          fullName={fullName}
          onChange={(field, value) => {
            if (field === 'password') setPassword(value)
            else setConfirm(value)
          }}
          onAcceptableChange={setPasswordAcceptable}
        />
      )}

      {step === 3 && (
        <StepTwoFactor
          username={username}
          secret={secret}
          qrSvg={qrSvg}
          code={totpCode}
          verified={totpVerified}
          onEnrolled={(newSecret, newQr) => {
            setSecret(newSecret)
            setQrSvg(newQr)
          }}
          onChange={setTotpCode}
          onVerified={setTotpVerified}
        />
      )}

      {step === 4 && (
        <StepReview
          fullName={fullName}
          username={username}
          email={email}
          orgName={orgName}
          timezone={timezone}
          hasLogo={logoFilename !== null}
        />
      )}

      <div className="mt-6 flex items-center justify-between gap-3 border-t border-border pt-4">
        <Button
          type="button"
          variant="ghost"
          onClick={() => setStep(step - 1)}
          disabled={step === 0 || complete.isPending}
        >
          Back
        </Button>

        <span className="text-sm text-text-dim">
          Step {step + 1} of {STEPS.length}
        </span>

        {step < STEPS.length - 1 ? (
          <Button
            type="button"
            variant="primary"
            onClick={() => setStep(step + 1)}
            disabled={!canAdvance}
          >
            Continue
          </Button>
        ) : (
          <Button type="button" variant="primary" onClick={submit} disabled={complete.isPending}>
            {complete.isPending ? 'Creating…' : 'Finish setup'}
          </Button>
        )}
      </div>
    </AuthLayout>
  )
}
