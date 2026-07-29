// Empty states that teach rather than merely report (SPEC §9.1).

import type { ReactNode } from 'react'

interface Props {
  title: string
  description: string
  action?: ReactNode
}

export function EmptyState({ title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <p className="text-base font-medium text-text">{title}</p>
      <p className="max-w-sm text-sm text-text-muted">{description}</p>
      {action !== undefined && <div className="mt-2">{action}</div>}
    </div>
  )
}
