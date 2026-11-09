/**
 * SPEC-VALUE-ICONS: the icons a product's spec values print, on the Specifications tab.
 *
 * Owner rulings 9 Nov ~14:25: inline after the value (1a); clicking opens the spec key's record
 * for `dealer_kit.library.manage` holders, a tooltip only for everyone else (2a); only
 * `dealer_kit.tag_templates.view` holders see icons, with no RBAC change (3a); nothing when a
 * value has no icon (5a).
 */
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, renderHook, screen, waitFor } from '@testing-library/react';

import { SpecValueIcons } from './SpecValueIcons';
import { useSpecValueIcons } from '../../hooks/useSpecValueIcons';
import { resetKitLibraryCache } from '@/lib/dealer-kit/kit-library-cache';
import type { SpecTableRow } from '@/components/spec-table';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const permissions = { set: new Set<string>(), isLoading: false };
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissionSet: permissions.set, isLoading: permissions.isLoading }),
}));

const listFeatureIcons = vi.fn();
vi.mock('@/app/(protected)/dealer-kit/services/tagDataService', () => ({
  listFeatureIcons: () => listFeatureIcons(),
}));

const ICONS = [
  { id: 'hot', name: 'Hot water', spec_key: 'water_supply', values: ['mixer'], url: 'https://cdn/hot.png' },
  { id: 'cold', name: 'Cold water', spec_key: 'water_supply', values: ['mixer'], url: 'https://cdn/cold.png' },
  { id: 'smart', name: 'Smart', spec_key: 'is_smart', values: ['true'], url: null },
];

function row(over: Partial<SpecTableRow>): SpecTableRow {
  return {
    specKey: 'water_supply',
    label: 'Water supply',
    value: 'mixer',
    unit: null,
    dataType: 'text',
    options: [],
    source: 'derived',
    evidence: null,
    unknownKey: false,
    valueLabels: {},
    conflict: null,
    ...over,
  };
}

beforeEach(() => {
  resetKitLibraryCache();
  listFeatureIcons.mockReset().mockResolvedValue(ICONS);
  permissions.set = new Set();
  permissions.isLoading = false;
});
afterEach(cleanup);

describe('SpecValueIcons', () => {
  it('draws each icon with its name as the tooltip, in order', () => {
    render(<SpecValueIcons specKey="water_supply" label="Water supply" icons={ICONS.slice(0, 2)} canManage={false} />);
    const names = Array.from(document.querySelectorAll('[data-spec-icon]')).map((el) =>
      el.getAttribute('title'),
    );
    expect(names).toEqual(['Hot water', 'Cold water']);
    expect(screen.getAllByRole('img').length).toBeGreaterThanOrEqual(2);
  });

  it('links to the spec key record (Choices and words) for a library manager', () => {
    render(<SpecValueIcons specKey="water_supply" label="Water supply" icons={ICONS.slice(0, 1)} canManage />);
    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe(
      '/master-data-management/product-specifications/water_supply?tab=choices',
    );
    expect(link.getAttribute('title')).toBe('Hot water');
  });

  it('is a tooltip only, no link, for anyone else', () => {
    render(<SpecValueIcons specKey="water_supply" label="Water supply" icons={ICONS.slice(0, 1)} canManage={false} />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('renders nothing when the value has no icon', () => {
    const { container } = render(
      <SpecValueIcons specKey="colour" label="Colour" icons={[]} canManage />,
    );
    expect(container.innerHTML).toBe('');
  });
});

describe('useSpecValueIcons', () => {
  it('never fetches the list without dealer_kit.tag_templates.view, and shows nothing', async () => {
    permissions.set = new Set(['master_data.products.view', 'dealer_kit.library.manage']);
    const { result } = renderHook(() => useSpecValueIcons());
    await new Promise((r) => setTimeout(r, 20));
    expect(listFeatureIcons).not.toHaveBeenCalled();
    expect(result.current.iconsFor(row({}))).toEqual([]);
  });

  it("returns a row's icons by its stored value once the list is in", async () => {
    permissions.set = new Set(['dealer_kit.tag_templates.view']);
    const { result } = renderHook(() => useSpecValueIcons());
    await waitFor(() => expect(result.current.iconsFor(row({})).map((i) => i.id)).toEqual(['hot', 'cold']));
    expect(result.current.canManage).toBe(false);
    expect(result.current.iconsFor(row({ specKey: 'is_smart', value: true })).map((i) => i.id)).toEqual(['smart']);
    // A conflict row holds its authored value, and that is what prints.
    expect(
      result.current
        .iconsFor(row({ value: 'mixer', conflict: { proposed: 'cold_only', proposedUnit: null } }))
        .map((i) => i.id),
    ).toEqual(['hot', 'cold']);
  });

  it('gives nothing for a key no longer in the registry, or a draft row with no value', async () => {
    permissions.set = new Set(['dealer_kit.tag_templates.view', 'dealer_kit.library.manage']);
    const { result } = renderHook(() => useSpecValueIcons());
    await waitFor(() => expect(result.current.iconsFor(row({})).length).toBe(2));
    expect(result.current.canManage).toBe(true);
    expect(result.current.iconsFor(row({ unknownKey: true }))).toEqual([]);
    expect(result.current.iconsFor(row({ value: null }))).toEqual([]);
  });

  it('shows nothing while permissions are still loading', () => {
    permissions.set = new Set(['dealer_kit.tag_templates.view']);
    permissions.isLoading = true;
    renderHook(() => useSpecValueIcons());
    expect(listFeatureIcons).not.toHaveBeenCalled();
  });
});
