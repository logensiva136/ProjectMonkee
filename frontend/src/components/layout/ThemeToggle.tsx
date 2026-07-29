// Dark/light theme switch in the top bar. Reads and writes the Zustand store in
// src/stores/theme.ts, which persists the choice to localStorage.

import { Moon, Sun } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { useThemeStore } from '@/stores/theme'

export function ThemeToggle() {
  // Selecting individual fields (rather than the whole store) means this
  // component only re-renders when those specific values change.
  const theme = useThemeStore((state) => state.theme)
  const toggleTheme = useThemeStore((state) => state.toggleTheme)

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
    >
      {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}
