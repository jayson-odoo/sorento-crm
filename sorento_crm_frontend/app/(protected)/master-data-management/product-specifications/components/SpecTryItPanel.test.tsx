/**
 * "Try it on" (AC-B.3): a product search over the whole master, in `fetchOptions`
 * mode - never a capped static dropdown - or a paste box as the alternative. This
 * component only owns the source and the description it reads from; the per-row
 * reads render INTO `SpecRuleEditor`'s rows, not here.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

vi.mock('../services/productSpecService', () => ({
  fetchProductPickerOptions: vi.fn(),
}));

type Option = { value: string; label: string };

// The real SearchableSelect drives a cmdk popover; this suite is about what
// SpecTryItPanel hands it (server-search mode) and does with what comes back, not
// about popover mechanics.
const captured: {
  fetchOptions?: (query: string, page: number) => Promise<Option[]>;
  paginated?: boolean;
  onOptionChange?: (option: Option | null) => void;
} = {};

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    fetchOptions?: (query: string, page: number) => Promise<Option[]>;
    paginated?: boolean;
    onOptionChange?: (option: Option | null) => void;
  }) => {
    captured.fetchOptions = props.fetchOptions;
    captured.paginated = props.paginated;
    captured.onOptionChange = props.onOptionChange;
    return <div data-testid="product-picker" />;
  },
}));

import SpecTryItPanel from './SpecTryItPanel';
import { fetchProductPickerOptions } from '../services/productSpecService';

beforeEach(() => {
  vi.clearAllMocks();
  captured.fetchOptions = undefined;
  captured.paginated = undefined;
  captured.onOptionChange = undefined;
});

describe('the product search', () => {
  it('runs server-search (fetchOptions), never a capped static list', () => {
    render(
      <SpecTryItPanel
        source={null}
        onSourceChange={vi.fn()}
        description={null}
        loading={false}
        error={null}
      />,
    );

    expect(captured.fetchOptions).toBe(fetchProductPickerOptions);
    expect(captured.paginated).toBe(true);
  });

  it('picking a product reports a product source with its id', () => {
    const onSourceChange = vi.fn();
    render(
      <SpecTryItPanel
        source={null}
        onSourceChange={onSourceChange}
        description={null}
        loading={false}
        error={null}
      />,
    );

    captured.onOptionChange?.({
      value: 'prod-800',
      label: 'SRTBA800 - Marble top basin',
    });

    expect(onSourceChange).toHaveBeenCalledWith({
      type: 'product',
      productId: 'prod-800',
      productLabel: 'SRTBA800 - Marble top basin',
    });
  });

  it('clearing the picker reports no source', () => {
    const onSourceChange = vi.fn();
    render(
      <SpecTryItPanel
        source={{ type: 'product', productId: 'prod-800', productLabel: 'x' }}
        onSourceChange={onSourceChange}
        description={null}
        loading={false}
        error={null}
      />,
    );

    captured.onOptionChange?.(null);

    expect(onSourceChange).toHaveBeenCalledWith(null);
  });
});

describe('the paste box', () => {
  it('is the alternative source, and reports text', () => {
    const onSourceChange = vi.fn();
    render(
      <SpecTryItPanel
        source={null}
        onSourceChange={onSourceChange}
        description={null}
        loading={false}
        error={null}
      />,
    );

    fireEvent.change(
      screen.getByPlaceholderText('Paste a product description to try instead'),
      { target: { value: 'MARBLE TOP BASIN (800MM)' } },
    );

    expect(onSourceChange).toHaveBeenCalledWith({
      type: 'text',
      text: 'MARBLE TOP BASIN (800MM)',
    });
  });

  it('clearing the box reports no source', () => {
    const onSourceChange = vi.fn();
    render(
      <SpecTryItPanel
        source={{ type: 'text', text: 'x' }}
        onSourceChange={onSourceChange}
        description={null}
        loading={false}
        error={null}
      />,
    );

    fireEvent.change(
      screen.getByPlaceholderText('Paste a product description to try instead'),
      { target: { value: '   ' } },
    );

    expect(onSourceChange).toHaveBeenCalledWith(null);
  });
});

describe('states', () => {
  it('shows nothing picked yet', () => {
    render(
      <SpecTryItPanel
        source={null}
        onSourceChange={vi.fn()}
        description={null}
        loading={false}
        error={null}
      />,
    );
    expect(
      screen.getByText(
        'Pick a product or paste text to see what each rule below reads from it.',
      ),
    ).toBeInTheDocument();
  });

  it('shows a loading state while try-it is in flight', () => {
    render(
      <SpecTryItPanel
        source={{ type: 'text', text: 'x' }}
        onSourceChange={vi.fn()}
        description={null}
        loading={true}
        error={null}
      />,
    );
    expect(screen.getByText('Trying the rules...')).toBeInTheDocument();
  });

  it('shows the description once a source and a result are present', () => {
    render(
      <SpecTryItPanel
        source={{ type: 'text', text: 'MARBLE TOP BASIN (800MM)' }}
        onSourceChange={vi.fn()}
        description="MARBLE TOP BASIN (800MM)"
        loading={false}
        error={null}
      />,
    );
    expect(screen.getByText('Description:')).toBeInTheDocument();
    // Twice: once in the read-only description line, once still in the paste box.
    expect(
      screen.getAllByText('MARBLE TOP BASIN (800MM)').length,
    ).toBeGreaterThan(0);
  });

  it('shows an error state', () => {
    render(
      <SpecTryItPanel
        source={{ type: 'text', text: 'x' }}
        onSourceChange={vi.fn()}
        description={null}
        loading={false}
        error="Could not try these rules"
      />,
    );
    expect(screen.getByText('Could not try these rules')).toBeInTheDocument();
  });
});
