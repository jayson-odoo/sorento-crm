/**
 * AddEditTopicModal — required-field validation (label + search prompt) and
 * hydrate-on-edit (an existing topic populates the form).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// jsdom polyfills for the SearchableSelect popover primitives.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

const scmOptions = vi.hoisted(() => ({ useCategoryOptions: vi.fn() }));
vi.mock('../../hooks/useScmOptions', () => scmOptions);

import { AddEditTopicModal } from './AddEditTopicModal';
import type { MarketResearchTopic } from '../types/market.types';

const EXISTING: MarketResearchTopic = {
  id: 't-1',
  label: 'Copper price index',
  category_ref: 'SRT-FC',
  currency: 'USD',
  search_prompt: 'copper LME price trend last 30 days',
  cadence: 'daily',
  is_active: false,
};

function renderModal(props: Partial<React.ComponentProps<typeof AddEditTopicModal>>) {
  const onSubmit = props.onSubmit ?? vi.fn().mockResolvedValue(undefined);
  render(
    <AddEditTopicModal
      open
      onOpenChange={vi.fn()}
      mode="create"
      initial={null}
      onSubmit={onSubmit}
      isSubmitting={false}
      {...props}
    />,
  );
  return { onSubmit };
}

beforeEach(() => {
  scmOptions.useCategoryOptions.mockReturnValue({ data: [], isLoading: false });
});

describe('AddEditTopicModal', () => {
  it('blocks submit and shows field errors when label + prompt are empty', async () => {
    const { onSubmit } = renderModal({ mode: 'create' });
    fireEvent.click(screen.getByRole('button', { name: /Add topic/i }));

    expect(await screen.findByText('Give the topic a short label.')).toBeInTheDocument();
    expect(screen.getByText('Enter the search prompt that drives the web search.')).toBeInTheDocument();
    expect(screen.getByText(/Please fix the highlighted fields before saving/i)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits a normalized body once required fields are filled', async () => {
    const { onSubmit } = renderModal({ mode: 'create' });
    fireEvent.change(screen.getByPlaceholderText(/Ceramic tile FX exposure/i), {
      target: { value: '  New Steel Topic  ' },
    });
    fireEvent.change(screen.getByPlaceholderText(/USD\/MYR exchange rate/i), {
      target: { value: '  steel rebar price  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Add topic/i }));

    await vi.waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        label: 'New Steel Topic',
        search_prompt: 'steel rebar price',
        category_ref: null,
        currency: null,
        cadence: 'weekly',
        is_active: true,
      }),
    );
  });

  it('hydrates the form from the topic being edited', () => {
    renderModal({ mode: 'edit', initial: EXISTING });
    expect(screen.getByText('Edit research topic')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Copper price index')).toBeInTheDocument();
    expect(screen.getByDisplayValue('copper LME price trend last 30 days')).toBeInTheDocument();
    // inactive topic hydrates the switch label to "Inactive"
    expect(screen.getByText('Inactive')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save changes/i })).toBeInTheDocument();
  });
});
