// Text input. The only input styling in the app.

import type { InputHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  /** Renders the error ring and sets aria-invalid for screen readers. */
  invalid?: boolean
  /** Machine data — codes, IDs, hashes — in JetBrains Mono (SPEC §9.1). */
  mono?: boolean
}

export function Input({ invalid = false, mono = false, className, ...rest }: Props) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={cn(
        'h-9 w-full rounded-md border bg-bg-subtle px-3 text-base text-text',
        'placeholder:text-text-dim',
        'transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-0',
        'disabled:cursor-not-allowed disabled:opacity-60',
        invalid ? 'border-sev-critical' : 'border-border hover:border-border-focus',
        mono && 'font-mono tabular-nums tracking-wide',
        className,
      )}
      {...rest}
    />
  )
}
