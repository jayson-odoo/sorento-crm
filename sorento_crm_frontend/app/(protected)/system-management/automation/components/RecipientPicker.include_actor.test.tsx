import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import RecipientPicker from './RecipientPicker';
import type { RecipientConfig } from '../types/automation.types';

// RecipientPicker fetches its users/roles lists on mount - stub both so the
// component settles without a real network call (same shape other
// system-management component tests use).
vi.mock('@/services/userSelectService', () => ({
  getUsersSelect: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
}));

const BASE_VALUE: RecipientConfig = {
  user_ids: [],
  role_ids: [],
  include_promotion_owner: false,
  include_assigned_cs_pic: false,
  extra_emails: [],
};

// AC-H16: "Cc the person who raised it" - a new key on RecipientConfig
// (`include_actor`), reusable by any trigger that puts `actor` in its
// context (PLAN-scm-oi-handover-email.md section 3.5).
describe('RecipientPicker - include_actor (AC-H16)', () => {
  it('ticking "Cc the person who raised it" calls onChange with include_actor: true', () => {
    const onChange = vi.fn();
    render(
      <RecipientPicker value={{ ...BASE_VALUE, include_actor: false } as RecipientConfig} onChange={onChange} />,
    );

    const checkbox = screen.getByLabelText(/Cc the person who raised it/i);
    fireEvent.click(checkbox);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ include_actor: true }),
    );
  });

  it('unticking calls onChange with include_actor: false', () => {
    const onChange = vi.fn();
    render(
      <RecipientPicker value={{ ...BASE_VALUE, include_actor: true } as RecipientConfig} onChange={onChange} />,
    );

    const checkbox = screen.getByLabelText(/Cc the person who raised it/i);
    fireEvent.click(checkbox);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ include_actor: false }),
    );
  });

  it('renders checked when the value already carries include_actor: true (round-trips on edit)', () => {
    render(
      <RecipientPicker value={{ ...BASE_VALUE, include_actor: true } as RecipientConfig} onChange={vi.fn()} />,
    );

    const checkbox = screen.getByLabelText(/Cc the person who raised it/i);
    expect(checkbox.getAttribute('aria-checked')).toBe('true');
  });

  it('sits beside the existing "assigned CS PIC" option', () => {
    render(<RecipientPicker value={BASE_VALUE} onChange={vi.fn()} />);

    // Both checkboxes exist on the same form - the new one is a sibling
    // control, not a replacement for the assigned-CS-PIC checkbox.
    expect(screen.getByLabelText(/Include assigned CS PIC/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Cc the person who raised it/i)).toBeInTheDocument();
  });
});

// AC-H26: "One email, everyone on the thread" - `one_email` on RecipientConfig,
// backing `_send_per_match`'s opt-in single-email dispatch shape.
describe('RecipientPicker - one_email (AC-H26)', () => {
  it('ticking "One email, everyone on the thread" calls onChange with one_email: true', () => {
    const onChange = vi.fn();
    render(
      <RecipientPicker value={{ ...BASE_VALUE, one_email: false } as RecipientConfig} onChange={onChange} />,
    );

    const checkbox = screen.getByLabelText(/One email, everyone on the thread/i);
    fireEvent.click(checkbox);

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ one_email: true }));
  });

  it('unticking calls onChange with one_email: false', () => {
    const onChange = vi.fn();
    render(
      <RecipientPicker value={{ ...BASE_VALUE, one_email: true } as RecipientConfig} onChange={onChange} />,
    );

    const checkbox = screen.getByLabelText(/One email, everyone on the thread/i);
    fireEvent.click(checkbox);

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ one_email: false }));
  });

  it('renders checked when the value already carries one_email: true (round-trips on edit)', () => {
    render(
      <RecipientPicker value={{ ...BASE_VALUE, one_email: true } as RecipientConfig} onChange={vi.fn()} />,
    );

    const checkbox = screen.getByLabelText(/One email, everyone on the thread/i);
    expect(checkbox.getAttribute('aria-checked')).toBe('true');
  });

  it('sits beside the existing "Cc the person who raised it" option', () => {
    render(<RecipientPicker value={BASE_VALUE} onChange={vi.fn()} />);

    expect(screen.getByLabelText(/Cc the person who raised it/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/One email, everyone on the thread/i)).toBeInTheDocument();
  });
});
