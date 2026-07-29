// A labelled form row: label, control, and either a hint or an error.
//
// Wrapping the control in <label> means clicking the label focuses the input
// without needing matching id/htmlFor attributes to be kept in sync.

import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface Props {
  label: string
  /** Replaces the hint and turns the row red when present. */
  error?: string | null
  hint?: ReactNode
  required?: boolean
  className?: string
  children: ReactNode
}

export function Field({ label, error, hint, required = false, className, children }: Props) {
  return (
    <label className={cn('flex flex-col gap-1.5', className)}>
      <span className="text-sm font-medium text-text-muted">
        {label}
        {required && (
          <span className="ml-1 text-sev-critical" aria-hidden="true">
            *
          </span>
        )}
      </span>

      {children}

      {error ? (
        <span role="alert" className="text-sm text-sev-critical">
          {error}
        </span>
      ) : (
        hint !== undefined && <span className="text-sm text-text-dim">{hint}</span>
      )}
    </label>
  )
}
