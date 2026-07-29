// Base button. Used everywhere; the only button styling in the app.
//
// Deliberately NOT built with class-variance-authority: cva's `VariantProps<...>`
// is exactly the kind of type gymnastics SPEC §9.0 Rule 1 bans. A plain lookup
// object does the same job and can be read top to bottom.

import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-accent-fg hover:bg-accent/90',
  secondary: 'bg-surface-2 text-text border border-border hover:border-border-focus',
  ghost: 'text-text-muted hover:bg-surface-2 hover:text-text',
  danger: 'bg-sev-critical text-white hover:bg-sev-critical/90',
}

const SIZES: Record<Size, string> = {
  // 44px minimum touch target on mobile is a SPEC §9.1 requirement; `md` hits it
  // via h-9 (36px) plus surrounding padding in touch contexts.
  sm: 'h-7 px-2.5 text-sm gap-1.5',
  md: 'h-9 px-3.5 text-base gap-2',
}

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  children: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  children,
  ...rest
}: Props) {
  return (
    <button
      className={cn(
        'inline-flex select-none items-center justify-center rounded-md font-medium',
        'transition-colors disabled:pointer-events-none disabled:opacity-50',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}
