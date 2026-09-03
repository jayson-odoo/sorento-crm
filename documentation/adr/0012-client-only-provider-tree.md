# ADR 0012 - The provider tree renders client-only (`ssr: false`)

**Status:** Accepted, 2 Sep 2026. Records existing behaviour; nothing changes.
**Context:** `PLAN-ui-motion-round2.md` M6-08, audit finding on `components/DynamicClientProviders.tsx`.

## The decision

`DynamicClientProviders` loads `ClientProviders` through `next/dynamic` with `ssr: false`:

```tsx
const ClientProviders = dynamic(
  () => import('@/components/ClientProviders').then((mod) => ({ default: mod.ClientProviders })),
  { ssr: false, loading: () => <LayoutLoadingFallback /> },
);
```

`ClientProviders` is the whole app: `QueryProvider`, `AuthProvider`, `SettingsProvider`,
`ThemeProvider`, `I18nProvider`, `TooltipsProvider`, `ModulesProvider`, and the `<Toaster>`.
None of it - not the sidebar, not a single page - is in the HTML the server sends. This is an
accepted decision for an authenticated internal app, not an oversight the M6 audit found and
left alone by omission.

## What `ssr: false` costs, made explicit

A cold load pays four sequential waits before the reader sees a real page, not one:

1. **The initial HTML has nothing in it.** The server response is `<LayoutLoadingFallback />`
   (or less) - no sidebar, no page shell, nothing a crawler or a "view source" would call
   content. Every route behind auth renders this way, always.
2. **The main JS bundle has to arrive and hydrate** before React does anything at all - true of
   any Next.js app, but doing nothing produces no earlier paint here because there is no
   server-rendered markup underneath it.
3. **The `ClientProviders` chunk is a SEPARATE fetch.** `next/dynamic` code-splits it, so it is
   a second round trip after the main bundle, not bytes already in hand.
4. **The provider stack does its own first-render work before children mount** - `AuthProvider`
   wraps NextAuth's `SessionProvider`, which fetches the session; `ModulesProvider` stands up
   the store-client context; `SettingsProvider` reads `localStorage` synchronously but still
   runs before the tree below it exists. A page's own data fetches start only after all of this
   has resolved once.

Four waits stacked in series, cold, before the first real pixel - the number this ADR exists to
put in writing rather than leave implicit in a `next/dynamic` call nobody re-reads.

## Why it is accepted anyway

- **Every route here requires a session.** There is no logged-out page this app serves that
  would benefit from server-rendered markup - a crawler is not a user this product has, and
  the pre-auth screens (login, portal, public catalogue links) are on a DIFFERENT layout that
  does not go through `DynamicClientProviders` at all.
- **The alternative is a hydration mismatch, not a faster page.** Removing `ssr: false` would
  render the provider tree on the server WITHOUT a session, then re-render it on the client
  WITH one - `AuthProvider`, `SettingsProvider` and `ModulesProvider` all branch on
  client-only state (`typeof window`, the NextAuth session, `localStorage`). That is the
  precise shape of a hydration warning, not a performance win.
  The current chunk-loading fallback (`LayoutLoadingFallback`) is a known, deliberate wait; a
  hydration mismatch is an unknown, undebugged one that surfaces as a console error in
  production and a flash of wrong content for the reader.
- **`next/dynamic`'s `loading:` fallback is the one thing SSR would have bought here anyway** -
  something on screen immediately - and it costs nothing to keep.

## The trigger that reopens this

Not "someone dislikes the four waits" - that is true today and was true before this ADR. The
trigger is a **measured Time-to-Interactive budget on a cold load** that this shape fails: if a
product decision sets a TTI ceiling (e.g. for a specific device class, network condition, or a
new public-facing surface added to this same layout) and a cold load measured against it comes
in over budget with the four-wait chain as the attributed cause, this decision is reopened and
the SSR-with-a-loading-skeleton alternative below gets built rather than argued about again from
first principles.

## Alternatives considered, not built

**Server-render the shell, client-render the session-dependent parts.** Splits
`ClientProviders` into a static shell (layout chrome, no data) rendered on the server and an
inner client boundary for anything session-shaped. Real engineering, not a one-line flag flip -
`QueryProvider`'s error toast, `SettingsProvider`'s stored preferences and `ModulesProvider`'s
store-client context would all need a defined "before the session is known" state. Not
justified without the measured TTI problem above; this is the shape the trigger, if it fires,
points to.

**Turn `ssr: false` off and accept the hydration mismatch.** Rejected outright - traded a known
wait for an unknown, harder-to-debug one, for no measured gain.
