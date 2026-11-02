/** DEALER-OI-ROUTE browser pass: the detail page shows the class condition read-only and
 * names Cc. */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import AutomationDetailPage from './page';

const automation = {
  id: 'a1',
  name: 'Order inquiry to dealer purchasing',
  description: null,
  enabled: true,
  trigger_type: 'order_inquiry_handover',
  trigger_config: {},
  action_type: 'send_email',
  email_template_id: 't1',
  email_template_name: 'OI handover',
  recipient_config: {
    user_ids: ['u1'],
    role_ids: [],
    include_promotion_owner: false,
    extra_emails: [],
    cc_user_ids: ['u2'],
    include_actor: true,
  },
  group_matches: false,
  conditions_json: { kind: 'group', combinator: 'and', rules: [] },
  conditions_text: 'Sales order class is Retail',
  schedule_type: 'manual',
  run_time: null,
  timezone: 'Asia/Kuala_Lumpur',
  last_run_at: null,
  last_status: null,
  last_error: null,
  next_run_at: null,
  created_by_user_id: null,
  created_at: '2026-11-01T00:00:00',
  updated_at: '2026-11-01T00:00:00',
};

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'a1' }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}));
vi.mock('../hooks/useAutomations', () => ({
  useAutomation: () => ({ data: automation, isLoading: false, refetch: vi.fn() }),
  useRunAutomationNow: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useToggleAutomation: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('../components/AutomationForm', () => ({ default: () => null }));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title }: { title: React.ReactNode }) => <h1>{title}</h1>,
}));
vi.mock('../components/AutomationRunsTable', () => ({ default: () => null }));

describe('Automation detail page', () => {
  it('shows the class condition read-only', () => {
    render(<AutomationDetailPage />);
    expect(screen.getByTestId('automation-conditions').textContent).toBe(
      'Sales order class is Retail',
    );
  });

  it('counts and lists To, Cc and the raiser', () => {
    render(<AutomationDetailPage />);
    expect(screen.getByText('Recipients (3)')).toBeInTheDocument();
    expect(screen.getByText('Cc users')).toBeInTheDocument();
    expect(screen.getByText('Cc the person who raised it')).toBeInTheDocument();
  });
});
