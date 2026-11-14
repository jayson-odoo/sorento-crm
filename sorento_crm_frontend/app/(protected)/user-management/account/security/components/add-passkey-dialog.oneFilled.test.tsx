/**
 * SIGNIN-2FA-NOT-ROLE fix round 2: one filled main button in the passkey "Confirm it's you"
 * dialog. It shares `OtpCodeField` with the portal verify card, where Send code is now the
 * filled primary; here the footer Continue is already the filled main action, so in phone mode
 * before any code is sent, exactly ONE button is filled and Send code is outline.
 *
 * `components/ui/button` marks its variant only through classes: the filled primary carries
 * `bg-primary`, the outline `border-input`.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const mutation = () => ({ mutateAsync: vi.fn(), isPending: false });
vi.mock('@/hooks/usePasskeys', () => ({
  useAddPasskeyMutation: () => mutation(),
  useSendPasskeyReauthCodeMutation: () => mutation(),
}));

import { AddPasskeyDialog } from './add-passkey-dialog';

function tokens(el: HTMLElement): string[] {
  return el.className.split(/\s+/).filter(Boolean);
}

function filledButtons(): HTMLElement[] {
  return screen.getAllByRole('button').filter((b) => tokens(b).includes('bg-primary'));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AddPasskeyDialog - one filled main button (phone mode, before a send)', () => {
  it('exactly one button is the filled primary, and it is Continue', async () => {
    render(<AddPasskeyDialog open onOpenChange={() => {}} hasPassword={false} />);
    await screen.findByLabelText(/verification code/i);

    const filled = filledButtons();
    expect(
      filled.map((b) => b.textContent?.trim()),
      'only one filled primary button may show',
    ).toHaveLength(1);
    expect(filled[0]).toHaveTextContent(/continue/i);
  });

  it('Send code is the outline variant here', async () => {
    render(<AddPasskeyDialog open onOpenChange={() => {}} hasPassword={false} />);
    const send = await screen.findByRole('button', { name: /^send code$/i });

    expect(tokens(send)).not.toContain('bg-primary');
    expect(tokens(send)).toContain('border-input');
  });
});
