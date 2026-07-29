// Inline message block. Severity is a 3px left border, never a full-colour
// background (SPEC §9.1 signature details).

import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Tone = 'error' | 'warning' | 'info' | 'success'

const TONES: Record<Tone, string> = {
  error: 'border-l-sev-critical text-sev-critical',
  warning: 'border-l-sev-medium text-sev-medium',
  info: 'border-l-sev-low text-text',
  success: 'border-l-ok text-ok',
}

interface Props {
  tone?: Tone
  title?: string
  className?: string
  children: ReactNode
}

export function Alert({ tone = 'info', title, className, children }: Props) {
  return (
    <div
      // `alert` announces immediately; `status` is polite. Errors interrupt,
      // confirmations wait their turn.
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn(
        'rounded-md border border-l-[3px] border-border bg-surface px-3 py-2.5 text-sm',
        TONES[tone],
        className,
      )}
    >
      {title !== undefined && <p className="font-medium">{title}</p>}
      <div className={cn(title !== undefined && 'mt-0.5', 'text-text-muted')}>{children}</div>
    </div>
  )
}
