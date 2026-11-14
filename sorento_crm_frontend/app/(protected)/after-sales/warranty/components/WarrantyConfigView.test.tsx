/**
 * AFTER-SALES-P2 red tests (UAC F3): the Warranty Configuration page, route `/after-sales/warranty`.
 *
 * Modules the coder builds: `app/(protected)/after-sales/warranty/page.tsx` (thin server page: Container + PageHeader
 * titled "Warranty Configuration") rendering `./WarrantyConfigView` default export, no props: three line tabs in the
 * order Policies / Kinds / Rules (URL `?tab=`, landing on Policies), each tab body being `PoliciesTab`, `KindsTab`,
 * `RulesTab` from this folder. The page-level header carries NO Create button: each tab has its own single one.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/warranty',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('./PoliciesTab', () => ({ PoliciesTab: () => <div data-testid="policies-tab" /> }));
vi.mock('./KindsTab', () => ({ KindsTab: () => <div data-testid="kinds-tab" /> }));
vi.mock('./RulesTab', () => ({ RulesTab: () => <div data-testid="rules-tab" /> }));

import WarrantyConfigView from './WarrantyConfigView';

beforeEach(() => window.history.replaceState({}, '', '/after-sales/warranty'));

describe('WarrantyConfigView', () => {
  it('has Policies, Kinds, Rules line tabs in order and lands on Policies', () => {
    render(<WarrantyConfigView />);
    expect(screen.getAllByRole('tab').map((t) => (t.textContent || '').trim())).toEqual(['Policies', 'Kinds', 'Rules']);
    expect(screen.getByTestId('policies-tab')).toBeInTheDocument();
    expect(screen.queryByTestId('kinds-tab')).toBeNull();
  });

  it('switches to Kinds and Rules', async () => {
    render(<WarrantyConfigView />);
    await userEvent.click(screen.getByRole('tab', { name: 'Kinds' }));
    expect(screen.getByTestId('kinds-tab')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Rules' }));
    expect(screen.getByTestId('rules-tab')).toBeInTheDocument();
  });

  it('opens the tab named in the URL', () => {
    window.history.replaceState({}, '', '/after-sales/warranty?tab=rules');
    render(<WarrantyConfigView />);
    expect(screen.getByTestId('rules-tab')).toBeInTheDocument();
  });

  it('has no Create button of its own', () => {
    render(<WarrantyConfigView />);
    expect(screen.queryByRole('button', { name: /^Create/ })).toBeNull();
  });
});
