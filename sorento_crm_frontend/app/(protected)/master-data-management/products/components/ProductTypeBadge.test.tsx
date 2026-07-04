import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ProductTypeBadge } from './ProductTypeBadge';

describe('ProductTypeBadge (products list Type column)', () => {
  it('renders "Variant" when the product is a variant', () => {
    render(<ProductTypeBadge isVariant={true} />);
    expect(screen.getByText('Variant')).toBeInTheDocument();
    expect(screen.queryByText('Base')).not.toBeInTheDocument();
  });

  it('renders "Base" when the product is not a variant', () => {
    render(<ProductTypeBadge isVariant={false} />);
    expect(screen.getByText('Base')).toBeInTheDocument();
    expect(screen.queryByText('Variant')).not.toBeInTheDocument();
  });

  it('defaults to "Base" when is_variant is undefined (list row without the field)', () => {
    render(<ProductTypeBadge />);
    expect(screen.getByText('Base')).toBeInTheDocument();
  });
});
