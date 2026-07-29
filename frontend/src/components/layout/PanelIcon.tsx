// Maps the icon name stored on a `panel` row to a lucide component.
//
// An explicit map rather than a dynamic lookup: it keeps the icon set a
// deliberate choice, it tree-shakes (a dynamic import would bundle all 1,500
// lucide icons), and an unknown name degrades to a neutral dot instead of
// crashing the sidebar.
//
// Adding a panel with a new icon means adding one line here.

import {
  Bell,
  Boxes,
  Circle,
  Globe,
  LayoutDashboard,
  Radar,
  Rss,
  ScrollText,
  Send,
  Settings,
  ShieldCheck,
  ShieldAlert,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

const ICONS: Record<string, LucideIcon> = {
  'layout-dashboard': LayoutDashboard,
  bell: Bell,
  rss: Rss,
  boxes: Boxes,
  globe: Globe,
  radar: Radar,
  send: Send,
  settings: Settings,
  'shield-check': ShieldCheck,
  'shield-alert': ShieldAlert,
  'scroll-text': ScrollText,
  users: Users,
  circle: Circle,
}

interface Props {
  name: string
  className?: string
}

export function PanelIcon({ name, className }: Props) {
  const Icon = ICONS[name] ?? Circle
  return <Icon className={className} aria-hidden="true" />
}
