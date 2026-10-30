/**
 * PORTAL-P4-REQUESTS L2 (owner a25895124 Q1 a, Q3 a): the contract a salesperson's CRM request list
 * keeps once it renders the PORTAL's own list body. Shared by the per-kind `*.portalList.test.tsx`.
 * Not a test file itself.
 */
import { expect } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { landingFieldsFor } from '@/app/(auth)/portal/lib/landing-fields';
import { LANDING_LABELS, type PortalLandingKind } from '@/app/(auth)/portal/lib/portal-client';

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

/** The URLs `apiFetch` was asked for (first argument of every call). */
export function urlsOf(apiFetch: { mock: { calls: unknown[][] } }): string[] {
  return apiFetch.mock.calls.map((c) => String(c[0]));
}

/** The smallest element holding both nodes. */
function commonAncestor(a: HTMLElement, b: HTMLElement): HTMLElement {
  let node: HTMLElement | null = a;
  while (node && !node.contains(b)) node = node.parentElement;
  return node ?? document.body;
}

export function filterButton(): HTMLElement {
  return screen.getByRole('button', { name: 'Filter' });
}

/** Cards by default, the toggle offers both views. */
export function expectViewToggle() {
  expect(screen.getByLabelText('List view')).toBeInTheDocument();
  expect(screen.getByLabelText('Board view')).toBeInTheDocument();
}

/** The Filter popover offers exactly the portal's fields for the kind. */
export async function expectPortalFilterFields(kind: PortalLandingKind) {
  fireEvent.click(filterButton());
  for (const field of landingFieldsFor(kind)) {
    await waitFor(() => expect(screen.getAllByText(field.label).length).toBeGreaterThan(0));
  }
}

/** "Create", exactly, in the same toolbar row as Filter and the view toggle (no card text in that row). */
export function expectCreateOnFilterRow(cardText: string) {
  const create = screen.getByLabelText('Create');
  expect(create.textContent?.trim()).toBe('Create');
  const row = commonAncestor(filterButton(), create);
  expect(row.contains(screen.getByLabelText('Board view'))).toBe(true);
  expect(row.textContent ?? '').not.toContain(cardText);
  return create;
}

/** No portal chrome: no kind picker, no welcome / log out header, no /portal links. */
export function expectNoPortalChrome(kind: PortalLandingKind) {
  expect(screen.queryByText(/welcome/i)).toBeNull();
  expect(screen.queryByText(/log ?out|sign ?out/i)).toBeNull();
  expect(document.querySelector('a[href^="/portal"]')).toBeNull();
  for (const [other, label] of Object.entries(LANDING_LABELS)) {
    if (other === kind) continue;
    expect(screen.queryByRole('tab', { name: label }), `kind picker offers ${label}`).toBeNull();
  }
}
