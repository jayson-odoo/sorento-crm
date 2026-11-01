import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

import RecipientPicker from './RecipientPicker';
import type { RecipientConfig } from '../types/automation.types';

vi.mock('@/services/userSelectService', () => ({
  getUsersSelect: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
}));

const BASE: RecipientConfig = {
  user_ids: [],
  role_ids: [],
  include_promotion_owner: false,
  extra_emails: [],
};

/** DEALER-OI-ROUTE: explicit To and Cc (`PLAN-dealer-oi-route-1nov.md`, AC-R6). */
describe('RecipientPicker - explicit To and Cc', () => {
  it('shows a To block and a Cc block', () => {
    render(<RecipientPicker value={BASE} onChange={vi.fn()} />);
    expect(screen.getByRole('group', { name: 'To' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Cc' })).toBeInTheDocument();
  });

  it('an email added under Cc lands on cc_emails, not extra_emails', () => {
    const onChange = vi.fn();
    render(<RecipientPicker value={BASE} onChange={onChange} />);
    const cc = within(screen.getByRole('group', { name: 'Cc' }));
    fireEvent.change(cc.getByPlaceholderText('someone@example.com'), {
      target: { value: 'cc@example.com' },
    });
    fireEvent.click(cc.getByRole('button', { name: 'Add' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ cc_emails: ['cc@example.com'], extra_emails: [] }),
    );
  });

  it('an email added under To lands on extra_emails', () => {
    const onChange = vi.fn();
    render(<RecipientPicker value={BASE} onChange={onChange} />);
    const to = within(screen.getByRole('group', { name: 'To' }));
    fireEvent.change(to.getByPlaceholderText('someone@example.com'), {
      target: { value: 'to@example.com' },
    });
    fireEvent.click(to.getByRole('button', { name: 'Add' }));
    const next = onChange.mock.calls[0][0] as RecipientConfig;
    expect(next.extra_emails).toEqual(['to@example.com']);
    expect(next.cc_emails ?? []).toEqual([]);
  });

  it('a saved Cc email shows under Cc and can be removed', () => {
    const onChange = vi.fn();
    render(
      <RecipientPicker value={{ ...BASE, cc_emails: ['old@example.com'] }} onChange={onChange} />,
    );
    const cc = within(screen.getByRole('group', { name: 'Cc' }));
    fireEvent.click(cc.getByRole('button', { name: 'Remove old@example.com' }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ cc_emails: [] }));
  });

  it('the person who raised it is a Cc option', () => {
    render(<RecipientPicker value={BASE} onChange={vi.fn()} />);
    const cc = within(screen.getByRole('group', { name: 'Cc' }));
    expect(cc.getByLabelText(/Cc the person who raised it/i)).toBeInTheDocument();
  });
});
