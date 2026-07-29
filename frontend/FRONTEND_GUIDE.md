# Frontend guide, for a Python developer

You write FastAPI, Pydantic and Celery daily. You do not write TypeScript or React. This document
exists so you can maintain this frontend alone, in production, without help.

The frontend is deliberately boring. There are no clever abstractions to learn. If something here
looks like it *should* be more elegant, that was the trade — readability won.

**Rules the code follows** (SPEC §9.0), so you can rely on them:

1. **API types are generated, never hand-written.** `src/types/api.gen.ts` comes from the backend's
   OpenAPI schema. Do not edit it.
2. **One component per file**, and the file is named after the component.
3. **The props interface sits directly above the component** in the same file. It is never imported
   from a shared types file.
4. **No wrappers around TanStack Query.** Every data hook is a plain `useQuery` in
   `features/<domain>/api.ts`.
5. **The backend is the source of truth.** Filtering, sorting, aggregation, permissions and derived
   values are computed in Python and arrive ready to render. When in doubt, add a field to the API
   response rather than compute it in a component.

---

## 1. Python → TypeScript / React

| Python | TypeScript / React |
|---|---|
| `class Vendor(BaseModel): ...` | `interface Vendor { ... }` |
| `name: str` | `name: string` |
| `count: int` / `score: float` | `count: number` (one number type — no int/float split) |
| `enabled: bool` | `enabled: boolean` |
| `Optional[str]` / `str \| None` | `name: string \| null` |
| a key that may be absent | `name?: string` (**different from `\| null`** — see §3.4) |
| `List[Vendor]` | `Vendor[]` |
| `Dict[str, str]` | `Record<string, string>` |
| `class Severity(str, Enum)` | `type Severity = 'critical' \| 'high' \| 'medium' \| 'low' \| 'info'` |
| `Tuple[int, int]` | `[number, number]` |
| `None` | `null` (and `undefined` — two flavours of nothing) |
| `f"{name} ({count})"` | `` `${name} (${count})` `` — backticks, not quotes |
| `[x.name for x in vendors]` | `vendors.map((v) => v.name)` |
| `[x for x in vendors if x.enabled]` | `vendors.filter((v) => v.enabled)` |
| `sum(v.score for v in vendors)` | `vendors.reduce((total, v) => total + v.score, 0)` |
| `any(v.is_kev for v in cves)` | `cves.some((c) => c.is_kev)` |
| `len(vendors)` | `vendors.length` |
| `sorted(vendors, key=lambda v: v.name)` | `[...vendors].sort((a, b) => a.name.localeCompare(b.name))` |
| `x if cond else y` | `cond ? x : y` |
| `value or default` | `value ?? default` (`??` only falls back on null/undefined; `\|\|` also falls back on `0` and `''`, which is usually a bug) |
| `d.get("a", {}).get("b")` | `d.a?.b` |
| `requests.get(url).json()` | `useQuery({ queryKey, queryFn })` |
| `def render(request): ...` | `export function Screen() { return <div/> }` |
| module-level mutable state | a Zustand store in `src/stores/` |
| Jinja `{% block content %}` | `<Outlet />` in a layout component |
| Jinja `{% for x in xs %}` | `{xs.map((x) => <Row key={x.id} ... />)}` |
| Jinja `{% if cond %}` | `{cond && <Thing />}` |
| `logging.getLogger(__name__)` | `console.log` (browser devtools console) |

### The one genuinely unfamiliar idea: re-rendering

A React component is a function that returns markup. React calls it again every time its data
changes and updates only the DOM that differs.

That means **the function body runs many times**. Do not put anything in it that should happen once
— an API call, a timer, writing to localStorage. Those go in a hook (`useQuery`, `useEffect`).

```tsx
export function VendorCount() {
  const vendors = useVendors()          // fine — a hook, React manages it
  const total = vendors.data?.length    // fine — recomputed each render, cheap
  // localStorage.setItem('seen', '1')  // WRONG — runs on every single render
  return <span>{total ?? 0}</span>
}
```

---

## 2. Where do I change X

The single most useful table here. Files marked *(Phase N)* do not exist yet — the row tells you
where that thing **will** live, so the map stays valid as the build progresses.

| I want to… | Open |
|---|---|
| Change any colour | `src/styles/tokens.css` — the only file defining a colour |
| Change severity colours specifically | `src/styles/tokens.css`, the `--sev-*` tokens |
| Add a colour token | `src/styles/tokens.css`, then map it in `tailwind.config.js` |
| Change fonts, text sizes, border radius | `tailwind.config.js` under `theme.extend` |
| Change global CSS, focus rings, scrollbars | `src/styles/index.css` |
| Change how a date/time is displayed | `src/lib/utils.ts` → `formatDateTime` / `formatAge` |
| Add a new screen | create `src/features/<domain>/`, register the route in `src/router.tsx`, seed a `panel` row in the backend |
| Change the route table | `src/router.tsx` |
| Change the top bar / wordmark | `src/components/layout/TopBar.tsx` |
| Change the footer status strip | `src/components/layout/StatusStrip.tsx` |
| Change the page chrome (header/footer arrangement) | `src/components/layout/AppLayout.tsx` |
| Change the dark/light toggle | `src/components/layout/ThemeToggle.tsx` + `src/stores/theme.ts` |
| Stop the theme flashing on reload | `public/theme-init.js` |
| Change what a form sends to the API | `src/features/<domain>/api.ts` |
| Change how errors from the API are surfaced | `src/lib/api.ts` (`ApiError`) |
| Change retry/caching behaviour for all queries | `src/lib/queryClient.ts` |
| Change button styling everywhere | `src/components/ui/Button.tsx` |
| Change card/panel styling everywhere | `src/components/ui/Card.tsx` |
| Change the loading placeholder | `src/components/ui/Skeleton.tsx` |
| Add a favicon or static file | `public/` |
| Change the page `<title>` or meta tags | `index.html` |
| Change security headers or the CSP | `nginx.conf` **and** `security-headers.conf` (read the comment in the latter first) |
| Change how `/api` is proxied in production | `nginx.conf` |
| Change how `/api` is proxied in local dev | `vite.config.ts` |
| Ban another TypeScript construct | `eslint.config.js` → `no-restricted-syntax` |
| **Add an item to the sidebar** | seed a `panel` row in `backend/app/seed/definitions.py` — the sidebar builds itself from `/me`, so `Sidebar.tsx` needs no edit |
| Change how the sidebar groups or highlights | `src/components/layout/Sidebar.tsx` |
| Add an icon for a new panel | `src/components/layout/PanelIcon.tsx` (one line) |
| Change what the command palette offers | `src/components/layout/CommandPalette.tsx` |
| Add or change a keyboard shortcut | `src/hooks/useKeyboardShortcuts.ts` + `ShortcutsHelp.tsx` |
| Change the onboarding wizard | `src/features/setup/` — one file per step |
| Change the password rules or strength meter | `backend/app/core/security.py` (the meter mirrors the backend) |
| Change the login or 2FA screen | `src/features/auth/LoginPage.tsx`, `MfaPage.tsx` |
| Change the user list columns | `src/features/admin/UserTable.tsx` |
| Change the permission or panel matrix | `src/features/admin/PermissionMatrix.tsx`, `PanelMatrix.tsx` |
| Change the audit row or its diff view | `src/features/admin/AuditRow.tsx` |
| Change session handling or silent refresh | `src/lib/api.ts` + `src/stores/auth.ts` |
| Add a column to the alerts table | `src/features/alerts/AlertTable.tsx` *(Phase 3)* |
| Add a filter to the vendor list | `src/features/vendors/VendorFilters.tsx` *(Phase 5)* |
| Change the nth-party graph layout | `src/features/vendors/VendorGraph.tsx` *(Phase 5)* |
| Change the rule condition builder | `src/features/rules/ConditionBuilder.tsx` *(Phase 3)* |
| Change the Telegram template editor | `src/features/telegram/TemplateEditor.tsx` *(Phase 3)* |

**Rule of thumb:** to change a screen, you only ever open `src/features/<that-screen>/`. Everything
for a feature — its components, its hooks, its API calls — lives together there.

---

## 3. The five errors you will actually hit

### 3.1 "I changed the data but the screen still shows the old value"

**Symptom.** A create/update succeeds, but the list still shows stale data until you reload.

**Cause.** TanStack Query cached the list. A mutation does not invalidate it automatically — it has
no way to know which queries a write affects.

**Fix.** Invalidate the affected query key after the mutation succeeds.

```tsx
const queryClient = useQueryClient()

const createVendor = useMutation({
  mutationFn: (body: VendorCreate) => apiPost('/vendors', body),
  onSuccess: () => {
    // "Anything cached under ['vendors'] is now stale — refetch it."
    queryClient.invalidateQueries({ queryKey: ['vendors'] })
  },
})
```

The key must match how the query declared it. `useQuery({ queryKey: ['vendors', filters] })` is
still invalidated by `['vendors']`, because matching is by prefix.

### 3.2 "Each child in a list should have a unique key prop"

**Symptom.** A console warning; sometimes rows visibly mix up their state when the list reorders.

**Cause.** React tracks list items by their `key` to know which DOM node belongs to which item.

**Fix.** Give every `.map()` a stable, unique `key` — a database ID, never the array index (an
index changes when the list reorders, which is exactly when it matters).

```tsx
{vendors.map((vendor) => <VendorRow key={vendor.id} vendor={vendor} />)}
```

### 3.3 "Maximum update depth exceeded" / an endless refetch loop

**Symptom.** The browser hangs, or the network tab shows the same request firing forever.

**Cause.** A `useEffect` dependency array containing a value that is recreated on every render.
Objects and arrays are compared by identity in JavaScript, not by value — `{a: 1} === {a: 1}` is
`false`. So a fresh object in the deps looks "changed" every render, the effect reruns, state
updates, and it renders again.

**Fix.** Depend on primitives, not objects.

```tsx
useEffect(() => { ... }, [filters])          // WRONG if `filters` is built inline
useEffect(() => { ... }, [filters.status])   // right — a string
```

The dependency array is "rerun this when one of these changes". `[]` means once on mount. Omitting
it entirely means every render, which is almost always a bug.

### 3.4 "Cannot read properties of undefined"

**Symptom.** A blank screen and a console error, usually on first load and never again.

**Cause.** The component rendered before the API responded. `data` is `undefined` at that point —
the single most common React crash for a backend developer, because in Python the data is simply
there by the time you render the template.

**Fix.** Handle the pending state explicitly. Every screen in this codebase does.

```tsx
const vendors = useVendors()

if (vendors.isPending) return <Skeleton className="h-20 w-full" />
if (vendors.isError) return <p className="text-sev-critical">Could not load vendors.</p>

return <VendorTable vendors={vendors.data} />   // data is guaranteed here
```

Note `isPending` (before the *first* response), not `isFetching` (true during background refetches
too — using it makes the panel flicker on every poll).

### 3.5 "The form will not submit and shows no error"

**Symptom.** Clicking submit does nothing. No network request, no visible message.

**Cause.** Zod validation failed on a field that is not being displayed — usually because the Zod
schema and the backend's Pydantic model disagree about optionality, or a `number` field is
receiving the string an `<input>` always produces.

**Fix.** Print the errors while debugging:

```tsx
const form = useForm({ resolver: zodResolver(schema) })
console.log(form.formState.errors)
```

For numeric inputs, coerce: `z.coerce.number()`. An `<input type="number">` still gives you a
string.

---

## 4. Running, building, debugging

### Everyday commands

Run from `frontend/`.

```bash
npm run dev
```

Vite dev server on http://localhost:5173 with hot reload. It proxies `/api` to
http://localhost:8000, so run the backend too (`docker compose up -d api`).

```bash
npm run typecheck
```

Runs `tsc --noEmit`. **This is your test suite.** There is no unit test layer on the frontend; the
type checker plus the generated API types are what catch mistakes. Run it before every commit.

```bash
npm run lint
```

ESLint. It enforces the SPEC §9.0 bans mechanically — enums, namespaces, conditional types, mapped
types, `infer`, abstract classes and decorators are all compile-time errors, with a message saying
so.

```bash
npm run format
```

Prettier. Also sorts Tailwind classes into a canonical order, so class-list diffs stay readable.

```bash
npm run build
```

Type-checks, then produces `dist/`. The Docker image runs this, so a type error fails the build
rather than shipping.

### Regenerating the API types

Do this whenever a backend Pydantic schema changes. The API must be running.

```bash
npm run types
```

It overwrites `src/types/api.gen.ts` from http://localhost:8000/api/v1/openapi.json. Then run
`npm run typecheck` — the compiler will point at every screen the change broke. That is the whole
point of generating them.

The file is committed on purpose: CI and `tsc` must work without a live backend, and its diff is
how a breaking API change gets noticed in review.

### Using a generated type

```tsx
import type { components } from '@/types/api.gen'

type Vendor = components['schemas']['Vendor']
```

Read `components['schemas']['Vendor']` like a dictionary lookup. That is the only "type expression"
you need in this codebase.

### Debugging in the browser

Open devtools (F12).

- **Console** — errors and anything you `console.log`.
- **Network** — filter to `Fetch/XHR` to see API calls, their status and their JSON. Check
  `X-Request-ID` on the response, then grep the backend logs for it (see the README runbook).
- **Elements** — inspect a node to see which Tailwind classes applied.

React state is not visible in plain devtools. Install the **React Developer Tools** extension to
inspect component props and state — it is the closest thing to a debugger here.

### When you are stuck

The stack is standard, so the official docs actually answer questions:

- TanStack Query (data fetching): https://tanstack.com/query/latest
- React (hooks reference): https://react.dev/reference/react
- Tailwind (class lookup): https://tailwindcss.com/docs
- React Router: https://reactrouter.com/en/main

And SPEC §9.0 is the constitution. If a proposed change requires a TypeScript construct that
section bans, the change is wrong — restructure it instead.
