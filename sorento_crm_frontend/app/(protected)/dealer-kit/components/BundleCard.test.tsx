import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BundleCard } from './BundleCard';
import { MOCK_RESOLVED_BUNDLE, MOCK_UNAVAILABLE_BUNDLE } from '../__mocks__/catalogue';

describe('BundleCard', () => {
  it('renders one priced heading with its components beneath', () => {
    render(<BundleCard bundle={MOCK_RESOLVED_BUNDLE} />);

    expect(screen.getByRole('heading', { name: /kitchen starter pack/i })).toBeInTheDocument();
    expect(screen.getByText('RM 1,800.00')).toBeInTheDocument();
    expect(screen.getByText(/undermount kitchen sink/i)).toBeInTheDocument();
    expect(screen.getByText(/pull-out kitchen mixer/i)).toBeInTheDocument();
  });

  it('shows the allocated figure on each component line', () => {
    render(<BundleCard bundle={MOCK_RESOLVED_BUNDLE} />);

    // The two allocations sum to the bundle price; showing both is what makes
    // an invoice explainable.
    expect(screen.getByText('RM 1,203.11')).toBeInTheDocument();
    expect(screen.getByText('RM 596.89')).toBeInTheDocument();
  });

  it('marks a bundle unavailable and names the component at fault', () => {
    render(<BundleCard bundle={MOCK_UNAVAILABLE_BUNDLE} />);

    expect(screen.getByText(/not currently available/i)).toBeInTheDocument();
    expect(screen.getByText(/wall-mounted sink tap is discontinued/i)).toBeInTheDocument();
    expect(screen.getByText(/^discontinued$/i)).toBeInTheDocument();
  });

  it('exposes availability on the element so a renderer cannot show it as orderable', () => {
    const { container } = render(<BundleCard bundle={MOCK_UNAVAILABLE_BUNDLE} />);

    expect(
      container.querySelector('[data-dk-bundle-available="false"]'),
    ).toBeInTheDocument();
  });

  it('still renders an unavailable bundle rather than hiding the block', () => {
    // Hiding it would leave a Designer wondering where their block went.
    render(<BundleCard bundle={MOCK_UNAVAILABLE_BUNDLE} />);

    expect(screen.getByRole('heading', { name: /shower combo/i })).toBeInTheDocument();
  });
});
