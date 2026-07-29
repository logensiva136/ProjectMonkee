// Application root: installs the providers every screen depends on.
//
// Providers are React's dependency injection. Anything rendered inside
// QueryClientProvider can call useQuery; the RouterProvider renders whichever
// route matches the URL.

import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { Toaster } from 'sonner'

import { queryClient } from '@/lib/queryClient'
import { router } from '@/router'

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      {/* Toasts inherit the design tokens rather than sonner's own palette. */}
      <Toaster
        position="bottom-right"
        toastOptions={{
          classNames: {
            toast: 'bg-surface border border-border text-text rounded-md',
            description: 'text-text-muted',
          },
        }}
      />
    </QueryClientProvider>
  )
}
