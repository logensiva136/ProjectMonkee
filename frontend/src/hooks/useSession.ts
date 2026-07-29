// Session bootstrap and the one hook screens ask "who am I, and what may I do".
//
// On a full page load the in-memory access token is gone (that is the point —
// see stores/auth.ts), so this attempts one silent refresh against the HttpOnly
// cookie before any guard is allowed to decide the user is signed out.

import { useEffect } from 'react'

import { useMe, useSetupStatus } from '@/features/auth/api'
import type { MeResponse } from '@/features/auth/api'
import { refreshAccessToken } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

export interface Session {
  /** True once the silent-refresh attempt has settled. Guards must wait for it. */
  isReady: boolean
  isAuthenticated: boolean
  needsSetup: boolean
  me: MeResponse | undefined
  hasPermission: (key: string) => boolean
  canViewPanel: (key: string) => boolean
}

/**
 * Restore the session once, at application start.
 *
 * Mounted exactly once, in App.tsx. The empty dependency array means "run this
 * on mount and never again" — React's equivalent of module-level init code.
 */
export function useAuthBootstrap(): void {
  const isInitialised = useAuthStore((state) => state.isInitialised)
  const setInitialised = useAuthStore((state) => state.setInitialised)

  useEffect(() => {
    if (isInitialised) return

    let cancelled = false
    refreshAccessToken().finally(() => {
      // The cleanup below flips `cancelled` if the component unmounted while
      // the request was in flight; setting state after that is a React warning
      // and, in a real app, a memory leak.
      if (!cancelled) setInitialised(true)
    })

    return () => {
      cancelled = true
    }
  }, [isInitialised, setInitialised])
}

export function useSession(): Session {
  const accessToken = useAuthStore((state) => state.accessToken)
  const isInitialised = useAuthStore((state) => state.isInitialised)

  const setup = useSetupStatus()
  const me = useMe(accessToken !== null)

  const permissions = new Set(me.data?.permissions ?? [])
  const panels = new Set((me.data?.panels ?? []).map((panel) => panel.key))

  return {
    isReady: isInitialised && !setup.isPending,
    isAuthenticated: accessToken !== null,
    needsSetup: setup.data?.needs_setup === true,
    me: me.data,
    hasPermission: (key: string) => permissions.has(key),
    canViewPanel: (key: string) => panels.has(key),
  }
}
