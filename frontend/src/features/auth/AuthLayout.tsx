// Shared chrome for the unauthenticated screens: login, MFA, and the wizard.
// Calls no API.

import type { ReactNode } from 'react'

interface Props {
  title: string
  subtitle?: string
  /** Widen for the onboarding wizard, which is denser than a login form. */
  wide?: boolean
  footer?: ReactNode
  children: ReactNode
}

export function AuthLayout({ title, subtitle, wide = false, footer, children }: Props) {
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(50%_100%_at_50%_0%,rgb(var(--accent)/0.06),transparent)]"
      />

      <main className="relative flex flex-1 items-center justify-center px-4 py-10">
        <div className={wide ? 'w-full max-w-2xl' : 'w-full max-w-sm'}>
          <div className="mb-6 text-center">
            <p className="font-mono text-lg font-medium tracking-[0.25em] text-text">HAYABUSA</p>
            <h1 className="mt-5 text-xl font-semibold text-text">{title}</h1>
            {subtitle !== undefined && <p className="mt-1 text-sm text-text-muted">{subtitle}</p>}
          </div>

          <div className="rounded-md border border-border bg-surface p-5">{children}</div>

          {footer !== undefined && <div className="mt-4 text-center text-sm">{footer}</div>}
        </div>
      </main>
    </div>
  )
}
