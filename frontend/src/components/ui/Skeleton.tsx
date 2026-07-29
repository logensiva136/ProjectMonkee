// Loading placeholder. SPEC §9.1: skeletons for content, never spinners —
// a skeleton preserves layout, so the page does not jump when data arrives.

import { cn } from '@/lib/utils'

interface Props {
  className?: string
}

export function Skeleton({ className }: Props) {
  return (
    <div aria-hidden="true" className={cn('animate-skeleton rounded bg-surface-2', className)} />
  )
}
