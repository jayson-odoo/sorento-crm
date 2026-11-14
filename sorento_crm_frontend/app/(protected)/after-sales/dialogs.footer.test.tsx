/**
 * R7-4: the footer (Cancel + main button) of every after-sales dialog stays in view. Only the field
 * area scrolls (a body with its own overflow); the panel itself never scrolls and the buttons sit
 * outside the scrolling element, so a tall form can never push Save below the visible bottom.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('./service-jobs/hooks/useServiceJobs', () => ({ useTechniciansSelect: () => ({ data: [] }) }));

import AssignTechnicianDialog from './service-jobs/components/AssignTechnicianDialog';
import ConfirmDateDialog from './service-jobs/components/ConfirmDateDialog';
import ReasonDialog from './service-jobs/components/ReasonDialog';
import ServiceJobFormDialog from './service-jobs/components/ServiceJobFormDialog';
import TechnicianFormDialog from './technicians/components/TechnicianFormDialog';

const noop = () => {};
const cases: Array<[string, string, React.ReactElement]> = [
  ['service job', 'Save', <ServiceJobFormDialog key="s" open onOpenChange={noop} onSubmit={noop} />],
  ['technician', 'Save', <TechnicianFormDialog key="t" open onOpenChange={noop} onSubmit={noop} />],
  ['confirm date', 'Confirm date', <ConfirmDateDialog key="c" open onOpenChange={noop} onSubmit={noop} />],
  ['assign technician', 'Assign technician', <AssignTechnicianDialog key="a" open onOpenChange={noop} onSubmit={noop} />],
  ['reason', 'Cancel job', <ReasonDialog key="r" open onOpenChange={noop} title="Cancel job" onSubmit={noop} />],
];

function ancestors(el: Element): Element[] {
  const out: Element[] = [];
  for (let n: Element | null = el.parentElement; n; n = n.parentElement) out.push(n);
  return out;
}

describe('after-sales dialogs keep their footer in view', () => {
  it.each(cases)('%s: the main button is in the footer, outside every scrolling element', (_n, label, element) => {
    render(<QueryClientProvider client={new QueryClient()}>{element}</QueryClientProvider>);
    const button = screen.getAllByRole('button', { name: label }).slice(-1)[0];
    expect(button.closest('[data-slot="dialog-footer"]')).not.toBeNull();
    expect(button.closest('[data-slot="dialog-body"]')).toBeNull();
    const scrolling = ancestors(button).filter((a) => /(^|\s)overflow-y-auto(\s|$)/.test(a.getAttribute('class') ?? ''));
    expect(scrolling).toEqual([]);
  });

  it.each(cases)('%s: the fields live in a body that scrolls on its own', (_n, _label, element) => {
    render(<QueryClientProvider client={new QueryClient()}>{element}</QueryClientProvider>);
    const body = screen.getByRole('dialog').querySelector('[data-slot="dialog-body"]');
    expect(body).not.toBeNull();
    expect(body!.className).toMatch(/overflow-y-auto/);
    expect(body!.className).toMatch(/min-h-0/);
  });
});
