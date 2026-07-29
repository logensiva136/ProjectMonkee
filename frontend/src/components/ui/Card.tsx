// Panel container: 1px hairline border on a raised surface.
//
// SPEC §9.1 uses hairline borders instead of drop shadows — shadows read as
// consumer software, borders read as a terminal.

import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface Props {
  /** Optional heading rendered in the card's header strip. */
  title?: string
  /** Small muted text beside the title, e.g. a count or a timestamp. */
  meta?: ReactNode
  /** Rendered at the right edge of the header, e.g. a button. */
  action?: ReactNode
  className?: string
  children: ReactNode
}

export function Card({ title, meta, action, className, children }: Props) {
  return (
    <section className={cn('rounded-md border border-border bg-surface', className)}>
      {title !== undefined && (
        <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <div className="flex items-baseline gap-2.5">
            <h2 className="text-base font-medium text-text">{title}</h2>
            {meta !== undefined && <span className="text-sm text-text-dim">{meta}</span>}
          </div>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}
