/** R6-5: every after-sales dialog names its description (the Radix aria-describedby warning). */
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
const cases: Array<[string, React.ReactElement]> = [
  ['Assign technician', <AssignTechnicianDialog key="a" open onOpenChange={noop} onSubmit={noop} />],
  ['Confirm date', <ConfirmDateDialog key="c" open onOpenChange={noop} onSubmit={noop} />],
  ['Reason', <ReasonDialog key="r" open onOpenChange={noop} title="Cancel" onSubmit={noop} />],
  ['Service job', <ServiceJobFormDialog key="s" open onOpenChange={noop} onSubmit={noop} />],
  ['Technician', <TechnicianFormDialog key="t" open onOpenChange={noop} onSubmit={noop} />],
];

describe('after-sales dialogs', () => {
  it.each(cases)('%s dialog has a description element', (_name, element) => {
    render(<QueryClientProvider client={new QueryClient()}>{element}</QueryClientProvider>);
    const dialog = screen.getByRole('dialog');
    const id = dialog.getAttribute('aria-describedby');
    expect(id).toBeTruthy();
    expect(document.getElementById(id as string)).not.toBeNull();
  });
});
