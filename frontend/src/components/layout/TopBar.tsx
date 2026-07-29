// Application top bar: wordmark and theme toggle.
//
// SPEC §9.1 allows exactly one gradient in the whole product — a barely-visible
// radial here. Everything else is flat with hairline borders.
//
// The sidebar, command palette and user menu land in Phase 1, when there are
// panels and a signed-in user to hang off them.

import { ThemeToggle } from '@/components/layout/ThemeToggle'

export function TopBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-bg/80 backdrop-blur">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_100%_at_50%_0%,rgb(var(--accent)/0.05),transparent)]"
      />
      <div className="relative flex h-12 items-center justify-between gap-4 px-4">
        <div className="flex items-baseline gap-2.5">
          <span className="font-mono text-base font-medium tracking-[0.2em] text-text">
            HAYABUSA
          </span>
          <span className="hidden text-sm text-text-dim sm:inline">
            threat &amp; attack surface monitoring
          </span>
        </div>
        <ThemeToggle />
      </div>
    </header>
  )
}
