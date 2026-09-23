import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import RecipientPicker from './RecipientPicker';
import type { RecipientConfig } from '../types/automation.types';

// Same fetch-stub shape `RecipientPicker.include_actor.test.tsx` uses - the component
// fetches its users/roles lists on mount.
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

/**
 * `PLAN-oi-request-cs-reserve.md` section 3.6, `oi-request-cs-reserve-acceptance-
 * criteria.md` AC-RS-29: two new checkboxes beside "Cc the person who raised it"
 * (`include_actor`) - "Cc the person who raised the inquiry" (`include_raiser`) and
 * "Cc the person who requested" (`include_requester`).
 *
 * TEST-FIRST (Phase 2): neither key exists on `RecipientPicker.tsx` today (measured -
 * the component renders exactly five checkboxes: promotion owner, assigned CS PIC,
 * include_actor, one_email, and the external-email adder has no checkbox at all) - a red
 * here is "no such checkbox", not an import typo.
 */
describe('RecipientPicker - include_raiser (AC-RS-29)', () => {
  it('ticking "Cc the person who raised the inquiry" calls onChange with include_raiser: true', () => {
    const onChange = vi.fn();
    render(
      <RecipientPicker
        value={{ ...BASE_VALUE, include_raiser: false } as RecipientConfig}
        onChange={onChange}
      />,
    );

    const checkbox = screen.getByLabelText(/Cc the person who raised the inquiry/i);
    fireEvent.click(checkbox);

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ include_raiser: true }));
  });

  it('renders checked when the value already carries include_raiser: true (round-trips on edit)', () => {
    render(
      <RecipientPicker
        value={{ ...BASE_VALUE, include_raiser: true } as RecipientConfig}
        onChange={vi.fn()}
      />,
    );

    const checkbox = screen.getByLabelText(/Cc the person who raised the inquiry/i);
    expect(checkbox.getAttribute('aria-checked')).toBe('true');
  });
});

describe('RecipientPicker - include_requester (AC-RS-29)', () => {
  it('ticking "Cc the person who requested" calls onChange with include_requester: true', () => {
    const onChange = vi.fn();
    render(
      <RecipientPicker
        value={{ ...BASE_VALUE, include_requester: false } as RecipientConfig}
        onChange={onChange}
      />,
    );

    const checkbox = screen.getByLabelText(/Cc the person who requested/i);
    fireEvent.click(checkbox);

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ include_requester: true }));
  });

  it('renders checked when the value already carries include_requester: true (round-trips on edit)', () => {
    render(
      <RecipientPicker
        value={{ ...BASE_VALUE, include_requester: true } as RecipientConfig}
        onChange={vi.fn()}
      />,
    );

    const checkbox = screen.getByLabelText(/Cc the person who requested/i);
    expect(checkbox.getAttribute('aria-checked')).toBe('true');
  });

  it('sits beside "Cc the person who raised it" - a sibling control, not a replacement', () => {
    render(<RecipientPicker value={BASE_VALUE} onChange={vi.fn()} />);

    expect(screen.getByLabelText(/Cc the person who raised it/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Cc the person who raised the inquiry/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Cc the person who requested/i)).toBeInTheDocument();
  });
});
