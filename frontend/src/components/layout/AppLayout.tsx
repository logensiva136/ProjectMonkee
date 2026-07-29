// Application chrome: top bar, routed page content, bottom status strip.
//
// <Outlet /> is React Router's placeholder for whichever child route matched —
// the equivalent of a Jinja `{% block content %}`. Routes are declared in
// src/router.tsx.

import { Outlet } from 'react-router-dom'

import { StatusStrip } from '@/components/layout/StatusStrip'
import { TopBar } from '@/components/layout/TopBar'

export function AppLayout() {
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <TopBar />
      <main className="flex-1">
        <Outlet />
      </main>
      <StatusStrip />
    </div>
  )
}
