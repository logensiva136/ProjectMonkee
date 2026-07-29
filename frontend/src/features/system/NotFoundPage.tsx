// Route: "*" — unknown path.
//
// SPEC §9.1 asks empty states to teach rather than just report. Calls no API.

import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 p-16 text-center">
      <span className="font-mono text-2xl text-text-dim">404</span>
      <h1 className="text-lg font-medium text-text">No screen at this address</h1>
      <p className="text-text-muted">
        The link may be from a later phase of the build, or simply mistyped.
      </p>
      <Link to="/" className="text-accent underline underline-offset-4 hover:no-underline">
        Back to system status
      </Link>
    </div>
  )
}
