// Theme state (dark / light), persisted per browser.
//
// Zustand is the equivalent of a module-level variable that React components can
// subscribe to. `useThemeStore` returns the current value and re-renders the
// component when it changes.
//
// SPEC §9.1: dark is the default; light is a first-class alternative and the
// choice is persisted.

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'hayabusa.theme'

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

/** Write the theme onto <html data-theme="..."> — the tokens key off it. */
function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'dark',
      setTheme: (theme: Theme) => {
        applyTheme(theme)
        set({ theme })
      },
      toggleTheme: () => {
        const next: Theme = get().theme === 'dark' ? 'light' : 'dark'
        applyTheme(next)
        set({ theme: next })
      },
    }),
    {
      name: STORAGE_KEY,
      // Runs after the persisted value is read back from localStorage. Without
      // it the store would hold the saved theme while the DOM still showed the
      // default, so the page would render in the wrong palette on reload.
      onRehydrateStorage: () => (state) => {
        applyTheme(state?.theme ?? 'dark')
      },
    },
  ),
)
