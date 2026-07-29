// Small coloured dot used in the footer status strip and dependency lists.
//
// SPEC §9.1 asks for restraint: a 6px dot carries the state, and the label
// beside it carries the meaning. No glow, no pulse, no icon.

import { cn } from '@/lib/utils'

export type Status = 'ok' | 'warn' | 'error' | 'unknown'

const COLOURS: Record<Status, string> = {
  ok: 'bg-ok',
  warn: 'bg-sev-medium',
  error: 'bg-sev-critical',
  unknown: 'bg-text-dim',
}

const LABELS: Record<Status, string> = {
  ok: 'Healthy',
  warn: 'Degraded',
  error: 'Failing',
  unknown: 'Unknown',
}

interface Props {
  status: Status
  className?: string
}

export function StatusDot({ status, className }: Props) {
  return (
    <span
      // Screen readers get a word; sighted users get the colour (SPEC §9.1
      // accessibility — colour is never the only channel).
      role="img"
      aria-label={LABELS[status]}
      className={cn('inline-block size-1.5 shrink-0 rounded-full', COLOURS[status], className)}
    />
  )
}
