/**
 * AC-1512 (chatbot-turn-rearch, S1): the Entity kinds DataGrid - column headers,
 * loading / empty / error / data states. Mirrors `ChatbotDomainsList.test.tsx`'s
 * convention (mock the data hook directly).
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type { ChatbotEntityKind } from '../types/chatbotEntityKind.types';

const useChatbotEntityKindsQuery = vi.fn();
const useHasPermission = vi.fn();

vi.mock('../hooks/useChatbotEntityKinds', () => ({
  useChatbotEntityKindsQuery: () => useChatbotEntityKindsQuery(),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => useHasPermission(slug),
}));
vi.mock('./ChatbotEntityKindModal', () => ({
  default: () => null,
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import ChatbotEntityKindsList from './ChatbotEntityKindsList';

const PRODUCT_KIND: ChatbotEntityKind = {
  code: 'product',
  label: 'Product',
  resolved_against: 'products (code, name, family)',
  did_you_mean: true,
  default_narrowing: 'narrow_to_code',
  family_grouping: 'by base code',
  base_property_words: { discontinued: 'is_discontinued' },
};

beforeEach(() => {
  useChatbotEntityKindsQuery.mockReset();
  useHasPermission.mockReset();
  useHasPermission.mockReturnValue(true);
});
afterEach(() => cleanup());

describe('ChatbotEntityKindsList - AC-1512', () => {
  it('renders the column headers and a real cell value per row (data state)', () => {
    useChatbotEntityKindsQuery.mockReturnValue({
      data: [PRODUCT_KIND],
      isLoading: false,
      isError: false,
    });
    render(<ChatbotEntityKindsList />);

    expect(screen.getByText('Kind')).toBeInTheDocument();
    expect(screen.getByText('Resolved against')).toBeInTheDocument();
    expect(screen.getByText('Did-you-mean')).toBeInTheDocument();
    expect(screen.getByText('Default narrowing')).toBeInTheDocument();
    expect(screen.getByText('Family grouping')).toBeInTheDocument();
    expect(screen.getByText('Base property words')).toBeInTheDocument();

    expect(screen.getByText('product')).toBeInTheDocument();
    expect(screen.getByText('products (code, name, family)')).toBeInTheDocument();
    expect(screen.getByText('by base code')).toBeInTheDocument();
    expect(screen.getByText('discontinued -> is_discontinued')).toBeInTheDocument();
  });

  it('renders without throwing while loading (data undefined, isLoading true)', () => {
    useChatbotEntityKindsQuery.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<ChatbotEntityKindsList />);
    expect(screen.getByText('Kind')).toBeInTheDocument();
  });

  it('renders the empty state with an Add kind action for a manager', () => {
    useChatbotEntityKindsQuery.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<ChatbotEntityKindsList />);
    expect(screen.getAllByRole('button', { name: /Add kind/i }).length).toBeGreaterThan(0);
  });

  it('hides Add kind from a user without chatbot_config.manage', () => {
    useHasPermission.mockReturnValue(false);
    useChatbotEntityKindsQuery.mockReturnValue({
      data: [PRODUCT_KIND],
      isLoading: false,
      isError: false,
    });
    render(<ChatbotEntityKindsList />);
    expect(screen.queryByRole('button', { name: /Add kind/i })).not.toBeInTheDocument();
  });

  it('renders the error state', () => {
    useChatbotEntityKindsQuery.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<ChatbotEntityKindsList />);
    expect(screen.getByText(/could not be loaded/i)).toBeInTheDocument();
  });
});
