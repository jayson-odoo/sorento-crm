/**
 * PORTAL-P3-ROLE-MENU round 3, T3: every project detail page that gates on
 * `projects.projects.view` also lets in a `projects.projects.view_own` holder (their own
 * project's detail, sales orders, POs, quotations ...). The gate is the real RequireAccess with
 * a mocked permission set; the heavy children are not rendered (the gate decides, the child is a
 * stub that only exists if the gate lets it through).
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const permsRef: { set: Set<string> } = { set: new Set() };
// The gate's contract is the permission(s) the page hands to RequireAccess: the stub applies them
// to the mocked permission set the way the real gate does (any of the listed slugs) and never
// renders the page's heavy children.
vi.mock('@/app/components/common/RequireAccess', () => ({
  default: ({ permission, anyPermission }: { permission?: string; anyPermission?: string[] }) => {
    const wanted = anyPermission ?? [permission as string];
    return wanted.some((p) => permsRef.set.has(p)) ? (
      <div data-testid="body" />
    ) : (
      <p>You don't have access to this page</p>
    );
  },
}));

const P = { projectId: 'p1' };
const params = (extra: Record<string, string> = {}) => ({ params: Promise.resolve({ ...P, ...extra }) });

type Case = [string, () => Promise<{ default: (props: never) => unknown }>, Record<string, string>];

const PAGES: Case[] = [
  ['[projectId]/page', () => import('./page') as never, {}],
  ['order-inquiries/page', () => import('./order-inquiries/page') as never, {}],
  ['delivery-schedules/[versionId]/page', () => import('./delivery-schedules/[versionId]/page') as never, { versionId: 'v1' }],
  ['purchase-orders/[versionId]/page', () => import('./purchase-orders/[versionId]/page') as never, { versionId: 'v1' }],
  ['quotations/[quotationId]/page', () => import('./quotations/[quotationId]/page') as never, { quotationId: 'q1' }],
  ['pos/[poId]/page', () => import('./pos/[poId]/page') as never, { poId: 'po1' }],
  ['sales-orders/[psoId]/page', () => import('./sales-orders/[psoId]/page') as never, { psoId: 's1' }],
  ['sales-orders/[psoId]/worksheet/page', () => import('./sales-orders/[psoId]/worksheet/page') as never, { psoId: 's1' }],
  ['sales-orders/[psoId]/divergence/page', () => import('./sales-orders/[psoId]/divergence/page') as never, { psoId: 's1' }],
  ['sales-orders/[psoId]/revisions/page', () => import('./sales-orders/[psoId]/revisions/page') as never, { psoId: 's1' }],
  [
    'quotation-documents/[documentId]/(view)/layout',
    () => import('./quotation-documents/[documentId]/(view)/layout') as never,
    { documentId: 'd1' },
  ],
];

async function renderPage(load: Case[1], extra: Record<string, string>, slugs: string[]) {
  permsRef.set = new Set(slugs);
  const mod = await load();
  const Page = mod.default as unknown as (props: unknown) => Promise<React.ReactElement>;
  const props = { ...params(extra), children: <span data-testid="child" /> };
  render(await Page(props));
}

describe.each(PAGES)('%s gate', (_name, load, extra) => {
  it('view_own only: the page body renders (no AccessDenied)', async () => {
    await renderPage(load, extra, ['projects.projects.view_own']);
    expect(screen.queryByText("You don't have access to this page")).toBeNull();
    expect(screen.getByTestId('body')).toBeInTheDocument();
  });

  it('view only: renders as today', async () => {
    await renderPage(load, extra, ['projects.projects.view']);
    expect(screen.queryByText("You don't have access to this page")).toBeNull();
    expect(screen.getByTestId('body')).toBeInTheDocument();
  });

  it('neither: AccessDenied as today', async () => {
    await renderPage(load, extra, ['sales.customer_asks.view']);
    expect(screen.getByText("You don't have access to this page")).toBeInTheDocument();
    expect(screen.queryByTestId('body')).toBeNull();
  });
});
