// Standard screen header: title, one-line explanation, optional actions.

import type { ReactNode } from 'react'

interface Props {
  title: string
  description?: string
  actions?: ReactNode
}

export function PageHeader({ title, description, actions }: Props) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-text">{title}</h1>
        {description !== undefined && (
          <p className="mt-0.5 text-sm text-text-muted">{description}</p>
        )}
      </div>
      {actions !== undefined && <div className="flex gap-2">{actions}</div>}
    </header>
  )
}
