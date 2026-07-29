// Top-bar user menu: identity, roles, sign out.
// Endpoint: POST /api/v1/auth/logout (via features/auth/api.ts)

import { useEffect, useRef, useState } from 'react'
import { LogOut, ShieldCheck, User } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { useLogout } from '@/features/auth/api'
import type { MeResponse } from '@/features/auth/api'
import { clearAuth } from '@/stores/auth'

interface Props {
  me: MeResponse
}

export function UserMenu({ me }: Props) {
  const navigate = useNavigate()
  const logout = useLogout()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Close on an outside click or Escape. The cleanup removes both listeners —
  // without it every mount would leave a listener behind on `document`.
  useEffect(() => {
    if (!open) return

    function handlePointer(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', handlePointer)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handlePointer)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  function signOut() {
    logout.mutate(undefined, {
      onSettled: () => {
        // Clear locally regardless of the request's outcome: a failed logout
        // must not leave someone stuck signed in on a shared machine.
        clearAuth()
        navigate('/login', { replace: true })
      },
    })
  }

  return (
    <div className="relative" ref={containerRef}>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className="flex size-5 items-center justify-center rounded-full bg-surface-2 text-[10px] font-semibold text-text-muted">
          {me.user.initials}
        </span>
        <span className="hidden sm:inline">{me.user.username}</span>
      </Button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-30 mt-1 w-60 rounded-md border border-border bg-surface p-1 shadow-lg"
        >
          <div className="border-b border-border px-2.5 py-2">
            <p className="truncate text-base text-text">{me.user.full_name}</p>
            <p className="machine truncate text-text-dim">{me.user.email}</p>
          </div>

          <div className="flex flex-wrap gap-1 border-b border-border px-2.5 py-2">
            {me.roles.map((role) => (
              <span
                key={role.key}
                className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-xs text-text-muted"
              >
                <ShieldCheck className="size-3" />
                {role.name}
              </span>
            ))}
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              navigate('/account')
            }}
            className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-base text-text-muted hover:bg-surface-2 hover:text-text"
          >
            <User className="size-4" />
            Account &amp; sessions
          </button>

          <button
            type="button"
            role="menuitem"
            onClick={signOut}
            disabled={logout.isPending}
            className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-base text-text-muted hover:bg-surface-2 hover:text-sev-critical"
          >
            <LogOut className="size-4" />
            {logout.isPending ? 'Signing out…' : 'Sign out'}
          </button>
        </div>
      )}
    </div>
  )
}
