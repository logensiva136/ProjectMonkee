// Small helpers used across the UI. Nothing domain-specific belongs here.

import { clsx } from 'clsx'
import type { ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Join Tailwind class names, letting later classes win over earlier ones.
 *
 * Plain string concatenation produces `"p-2 p-4"`, and which one applies then
 * depends on CSS source order rather than on the order you wrote them.
 * `twMerge` resolves that: `cn('p-2', 'p-4')` is `'p-4'`.
 *
 *   cn('rounded-md border', isActive && 'border-accent')
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/**
 * Render a UTC timestamp from the API in the operator's local time.
 *
 * The backend stores and returns everything in UTC (SPEC §5); display is the
 * only place a timezone is applied.
 */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

/** "4s ago", "12m ago", "3h ago" — for freshness indicators. */
export function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  return `${Math.round(seconds / 86400)}d ago`
}
