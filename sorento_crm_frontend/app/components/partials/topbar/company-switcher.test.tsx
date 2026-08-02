import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CompanySwitcher } from './company-switcher';
import type { ActiveCompany } from '@/app/providers/CompanyProvider';

const useCompanyMock = vi.fn();

vi.mock('@/app/providers/CompanyProvider', () => ({
  useCompany: () => useCompanyMock(),
}));

const SORENTO: ActiveCompany = {
  id: 'c1',
  name: 'Sorento',
  code: 'SRT',
  is_active: true,
};
const MOCHA: ActiveCompany = {
  id: 'c2',
  name: 'Mocha',
  code: 'MCH',
  is_active: true,
};

function setContext(grants: ActiveCompany[], activeCompany: ActiveCompany | null) {
  useCompanyMock.mockReturnValue({
    companies: grants,
    grants,
    activeCompany,
    setActiveCompany: vi.fn(),
    isLoading: false,
  });
}

describe('CompanySwitcher', () => {
  beforeEach(() => {
    useCompanyMock.mockReset();
  });

  it('renders a read-only indicator (no dropdown trigger) for a single-grant user', () => {
    setContext([SORENTO], SORENTO);
    render(<CompanySwitcher />);

    expect(screen.getByTestId('company-indicator')).toBeInTheDocument();
    expect(screen.getByText('Sorento')).toBeInTheDocument();
    expect(screen.getByText('SRT')).toBeInTheDocument();
    // informational only — nothing to switch to
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders the switchable dropdown trigger when the user has more than one grant', () => {
    setContext([SORENTO, MOCHA], SORENTO);
    render(<CompanySwitcher />);

    expect(screen.queryByTestId('company-indicator')).toBeNull();
    const trigger = screen.getByRole('button', { name: /Sorento/ });
    expect(trigger).toHaveAttribute('title', 'Switch active company');
  });

  it('renders nothing while loading or with zero grants', () => {
    setContext([], null);
    const { container } = render(<CompanySwitcher />);
    expect(container).toBeEmptyDOMElement();
  });
});
