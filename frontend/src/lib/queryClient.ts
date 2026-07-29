// TanStack Query configuration.
//
// TanStack Query is the server-state cache: it fetches, caches, dedupes and
// refetches. Think of it as `requests.get` plus a cache that knows when its
// contents went out of date.
//
// Defaults live here so individual hooks stay two lines long (SPEC §9.0 Rule 3
// forbids wrapping useQuery in custom abstractions).

import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '@/lib/api'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // How long fetched data is considered fresh. Within this window,
      // remounting a component reads the cache instead of refetching.
      staleTime: 30_000,
      // Refetching on every window focus is noisy on an always-open console.
      refetchOnWindowFocus: false,
      retry: (failureCount: number, error: unknown) => {
        // 4xx means the request was wrong; repeating it will not help. Retry
        // only server errors and network failures, and only twice.
        if (error instanceof ApiError && error.status < 500) return false
        return failureCount < 2
      },
    },
    mutations: {
      // A failed write must surface, not silently retry and possibly duplicate.
      retry: false,
    },
  },
})
