// Progress indicator across the five wizard steps. Calls no API.

import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'

interface Props {
  steps: string[]
  /** Zero-based index of the step currently being edited. */
  current: number
}

export function Stepper({ steps, current }: Props) {
  return (
    <ol className="mb-6 flex items-center gap-1" aria-label="Setup progress">
      {steps.map((label, index) => {
        const done = index < current
        const active = index === current

        return (
          <li key={label} className="flex flex-1 items-center gap-2">
            <span
              aria-current={active ? 'step' : undefined}
              className={cn(
                'flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium',
                done && 'border-accent bg-accent text-accent-fg',
                active && 'border-accent text-accent',
                !done && !active && 'border-border text-text-dim',
              )}
            >
              {done ? <Check className="size-3.5" /> : index + 1}
            </span>

            {/* Labels are noise on a narrow screen; the numbers still convey
                position, so they are hidden rather than wrapped. */}
            <span
              className={cn(
                'hidden truncate text-sm sm:inline',
                active ? 'text-text' : 'text-text-dim',
              )}
            >
              {label}
            </span>

            {index < steps.length - 1 && (
              <span
                aria-hidden="true"
                className={cn('h-px flex-1', done ? 'bg-accent' : 'bg-border')}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}
