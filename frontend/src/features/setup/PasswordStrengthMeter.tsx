// Live password strength feedback for wizard step 3.
// Data comes from POST /api/v1/setup/password-check via useCheckPassword().
//
// The score and the problem list both come from the backend, which runs the
// identical policy `/setup/complete` enforces — so the meter can never say
// "strong" for a password the final submit will reject (SPEC §9.0 Rule 6).

import { cn } from '@/lib/utils'
import type { PasswordCheckResponse } from '@/features/setup/api'

const LABELS = ['Very weak', 'Weak', 'Fair', 'Strong', 'Very strong']
const BAR_COLOURS = ['bg-sev-critical', 'bg-sev-critical', 'bg-sev-medium', 'bg-ok', 'bg-ok']

interface Props {
  result: PasswordCheckResponse | undefined
  /** True while a check is in flight, so the bar does not flicker to zero. */
  isChecking: boolean
  hasInput: boolean
}

export function PasswordStrengthMeter({ result, isChecking, hasInput }: Props) {
  if (!hasInput) return null

  const score = result?.score ?? 0
  const acceptable = result?.acceptable ?? false

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="flex h-1 flex-1 gap-1" role="presentation">
          {[0, 1, 2, 3, 4].map((index) => (
            <span
              key={index}
              className={cn(
                'h-full flex-1 rounded-full transition-colors',
                index <= score && result !== undefined ? BAR_COLOURS[score] : 'bg-border',
              )}
            />
          ))}
        </div>
        <span
          className={cn(
            'w-24 shrink-0 text-right text-sm',
            acceptable ? 'text-ok' : 'text-text-muted',
          )}
        >
          {isChecking && result === undefined ? 'Checking…' : LABELS[score]}
        </span>
      </div>

      {result !== undefined && result.problems.length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-4 text-sm text-sev-critical">
          {result.problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}

      {result !== undefined && result.problems.length === 0 && (
        <p className="text-sm text-text-dim">
          Offline cracking estimate:{' '}
          <span className="machine text-text-muted">{result.crack_time}</span>
        </p>
      )}
    </div>
  )
}
