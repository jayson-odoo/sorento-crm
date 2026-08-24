import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SlaExtendMenuItem, SlaExtendDialog } from './SlaExtendAction';

let hasPerm = true;
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => hasPerm,
}));

// Effective (impersonation-aware) acting user = 'me'; tracker assigned to 'me' by default.
vi.mock('@/hooks/useEffectiveUserId', () => ({
  useEffectiveUserId: () => 'me',
}));

// DropdownMenuItem must render outside a menu in the test - stub to a button.
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children, onSelect }: any) => (
    <button onClick={() => onSelect?.({ preventDefault() {} })}>{children}</button>
  ),
}));

// Capture the props handed to the reused conversation ExtendDueDialog.
const extendDialogProps = vi.fn();
vi.mock(
  '@/app/(protected)/sla-management/conversation-sla-tracking/components/ExtendDueDialog',
  () => ({
    default: (props: any) => {
      extendDialogProps(props);
      return props.open ? <div data-testid="extend-dialog" /> : null;
    },
  }),
);

const tracker: any = {
  id: 'trk-1',
  is_resolved: false,
  due_at_resolution: '2026-07-01T09:00:00',
  assigned_to_id: 'me', // current user is the assignee
};

describe('SlaExtendMenuItem (F1/F2)', () => {
  it('renders for the assignee with an active unresolved tracker + the perm', () => {
    hasPerm = true;
    render(<SlaExtendMenuItem activeTracker={tracker} onSelect={() => {}} />);
    expect(screen.getByText('Extend SLA')).toBeInTheDocument();
  });

  it('hidden when the user is NOT the current assignee (assignee-only)', () => {
    hasPerm = true;
    const { container } = render(
      <SlaExtendMenuItem activeTracker={{ ...tracker, assigned_to_id: 'someone-else' }} onSelect={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('hidden without the extend permission', () => {
    hasPerm = false;
    const { container } = render(<SlaExtendMenuItem activeTracker={tracker} onSelect={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('hidden when there is no active tracker', () => {
    hasPerm = true;
    const { container } = render(<SlaExtendMenuItem activeTracker={null} onSelect={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('hidden when the tracker is resolved', () => {
    hasPerm = true;
    const { container } = render(
      <SlaExtendMenuItem activeTracker={{ ...tracker, is_resolved: true }} onSelect={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('SlaExtendDialog (F3)', () => {
  it('seeds the reused ExtendDueDialog with the tracker id + resolution due', () => {
    extendDialogProps.mockClear();
    render(
      <SlaExtendDialog
        activeTracker={tracker}
        label="Complaint · CMP-1"
        open
        onOpenChange={() => {}}
      />,
    );
    expect(screen.getByTestId('extend-dialog')).toBeInTheDocument();
    const props = extendDialogProps.mock.calls.at(-1)![0];
    expect(props.trackingId).toBe('trk-1');
    expect(props.currentDueAt).toBe('2026-07-01T09:00:00');
    expect(props.label).toBe('Complaint · CMP-1');
  });

  it('renders nothing without a tracker', () => {
    const { container } = render(
      <SlaExtendDialog activeTracker={null} open onOpenChange={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
