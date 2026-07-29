// Authentication state.
//
// The access token lives HERE, in memory, and nowhere else — not localStorage,
// not sessionStorage, not a readable cookie. Anything JavaScript can read,
// injected JavaScript can steal. Losing it on refresh is fine: the HttpOnly
// refresh cookie silently mints a new one (see lib/api.ts).
//
// `mfaToken` is the short-lived proof that the password step passed. It is not
// an access token and the API refuses it anywhere one is expected.

import { create } from 'zustand'

interface AuthState {
  accessToken: string | null
  mfaToken: string | null
  /** False until the first refresh attempt settles, so guards do not redirect early. */
  isInitialised: boolean

  setAccessToken: (token: string | null) => void
  setMfaToken: (token: string | null) => void
  setInitialised: (value: boolean) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  mfaToken: null,
  isInitialised: false,

  setAccessToken: (token: string | null) => set({ accessToken: token }),
  setMfaToken: (token: string | null) => set({ mfaToken: token }),
  setInitialised: (value: boolean) => set({ isInitialised: value }),
  clear: () => set({ accessToken: null, mfaToken: null }),
}))

/**
 * Read the token outside a React component.
 *
 * `useAuthStore(...)` is a hook and may only be called during render. The API
 * client needs the token from inside a plain async function, and `getState()`
 * is Zustand's non-reactive escape hatch for exactly that.
 */
export function getAccessToken(): string | null {
  return useAuthStore.getState().accessToken
}

export function setAccessToken(token: string | null): void {
  useAuthStore.getState().setAccessToken(token)
}

export function clearAuth(): void {
  useAuthStore.getState().clear()
}
