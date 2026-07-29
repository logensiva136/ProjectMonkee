// Route table. Adding a screen means adding a route here, creating
// features/<domain>/, and seeding a `panel` row in the backend (SPEC §6.3).
//
// Phase 0 has one route. The full map in SPEC §9.2 fills in from Phase 1.

import { createBrowserRouter } from 'react-router-dom'

import { AppLayout } from '@/components/layout/AppLayout'
import { NotFoundPage } from '@/features/system/NotFoundPage'
import { SystemStatusPage } from '@/features/system/SystemStatusPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <SystemStatusPage /> },
      // Catch-all. Nginx serves index.html for unknown paths so the SPA can
      // route them, which means an unknown URL lands here rather than 404ing
      // at the web server.
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
