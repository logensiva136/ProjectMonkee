// The organisation mark: uploaded logo, or the deterministic monogram.
// Data comes from GET /api/v1/me (org_logo_url, org_initials).

import { cn } from '@/lib/utils'

interface Props {
  logoUrl: string | null | undefined
  initials: string | null | undefined
  size?: 'sm' | 'md'
  className?: string
}

const SIZES = {
  sm: 'size-6 text-[10px]',
  md: 'size-9 text-sm',
}

export function OrgAvatar({ logoUrl, initials, size = 'sm', className }: Props) {
  if (logoUrl !== null && logoUrl !== undefined && logoUrl !== '') {
    return (
      <img
        src={logoUrl}
        alt=""
        className={cn(
          'shrink-0 rounded border border-border object-contain',
          SIZES[size],
          className,
        )}
      />
    )
  }

  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex shrink-0 items-center justify-center rounded border border-border bg-surface-2 font-semibold text-text-muted',
        SIZES[size],
        className,
      )}
    >
      {initials ?? '··'}
    </span>
  )
}
