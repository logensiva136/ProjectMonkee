// Application top bar: org mark, mobile menu button, palette trigger, theme,
// user menu.
// Data: GET /api/v1/me via useSession().
//
// SPEC §9.1 allows exactly one gradient in the product — a barely-visible
// radial here. Everything else is flat with hairline borders.

import { Menu, Search } from 'lucide-react'

import { OrgAvatar } from '@/components/layout/OrgAvatar'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { UserMenu } from '@/components/layout/UserMenu'
import { Button } from '@/components/ui/Button'
import type { MeResponse } from '@/features/auth/api'

interface Props {
  me: MeResponse | undefined
  onOpenPalette: () => void
  onOpenDrawer: () => void
}

export function TopBar({ me, onOpenPalette, onOpenDrawer }: Props) {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-bg/80 backdrop-blur">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_100%_at_50%_0%,rgb(var(--accent)/0.05),transparent)]"
      />

      <div className="relative flex h-12 items-center gap-3 px-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={onOpenDrawer}
          aria-label="Open navigation"
          className="lg:hidden"
        >
          <Menu className="size-4" />
        </Button>

        <div className="flex items-center gap-2.5">
          <OrgAvatar logoUrl={me?.org_logo_url} initials={me?.org_initials} />
          <span className="font-mono text-base font-medium tracking-[0.18em] text-text">
            HAYABUSA
          </span>
          {me?.org_name !== null && me?.org_name !== undefined && (
            <span className="hidden truncate text-sm text-text-dim md:inline">{me.org_name}</span>
          )}
        </div>

        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={onOpenPalette}
            className="hidden h-7 items-center gap-2 rounded-md border border-border bg-bg-subtle px-2.5 text-sm text-text-dim hover:border-border-focus hover:text-text-muted sm:flex"
          >
            <Search className="size-3.5" />
            Search
            <kbd className="machine rounded border border-border px-1 text-xs">Ctrl K</kbd>
          </button>

          <ThemeToggle />
          {me !== undefined && <UserMenu me={me} />}
        </div>
      </div>
    </header>
  )
}
