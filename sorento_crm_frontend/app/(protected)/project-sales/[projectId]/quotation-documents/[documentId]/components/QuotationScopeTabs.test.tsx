/**
 * The scope strip, after the client's Excel-sheet-tabs feedback.
 *
 * Two rules are worth pinning because both are one careless edit away from coming back:
 * adding a scope is a control INSIDE the strip (it used to be a page action pushed to the far
 * right of the screen), and money never appears beside a scope name until the reader asks for
 * that one scope's figure.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { QuotationScope } from '../../../../_shared/services/quotationDocumentService';
import { QuotationScopeTabs } from './QuotationScopeTabs';

function scope(overrides: Partial<QuotationScope> = {}): QuotationScope {
  return {
    id: 's1',
    scope_label: 'Townhouse',
    sort_order: 1,
    outcome: 'open',
    current_version_id: 'v1',
    current_version_no: 1,
    line_count: 4,
    scope_total: '235000.00',
    ...overrides,
  };
}

const scopes = [
  scope(),
  scope({ id: 's2', scope_label: 'Guard house', sort_order: 2, scope_total: '18420.50' }),
];

function renderTabs(props: Partial<React.ComponentProps<typeof QuotationScopeTabs>> = {}) {
  const onSelect = vi.fn();
  const onAddScope = vi.fn();
  render(
    <QuotationScopeTabs
      scopes={scopes}
      activeScopeId="s1"
      onSelect={onSelect}
      canEdit
      onAddScope={onAddScope}
      {...props}
    />,
  );
  return { onSelect, onAddScope };
}

describe('QuotationScopeTabs adding a scope', () => {
  it('puts the + at the end of the tab strip and adds from there', () => {
    const { onAddScope } = renderTabs();

    // Inside the strip, not a page action across the screen: this is the whole feedback.
    const strip = screen.getByRole('tablist');
    const add = within(strip).getByRole('button', { name: 'Add a scope' });
    expect(add).toBeInTheDocument();

    // Last control in the strip, the way a spreadsheet adds a sheet after the existing ones.
    const controls = within(strip).getAllByRole('button');
    expect(controls[controls.length - 1]).toBe(add);

    fireEvent.click(add);
    expect(onAddScope).toHaveBeenCalledTimes(1);
  });

  it('offers no + to a reader who cannot edit', () => {
    renderTabs({ canEdit: false });

    expect(screen.queryByRole('button', { name: 'Add a scope' })).not.toBeInTheDocument();
    // The tabs themselves still work: read-only is not the same as unusable.
    expect(screen.getByRole('tab', { name: 'Townhouse' })).toBeInTheDocument();
  });

  it('still renders the strip when the document has one scope only', () => {
    renderTabs({ scopes: [scope()] });

    expect(screen.getByRole('tab', { name: 'Townhouse' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add a scope' })).toBeInTheDocument();
  });
});

describe('QuotationScopeTabs revealing a value', () => {
  it('shows no money at all until a tab is asked', () => {
    renderTabs();

    // The tab reads as a name and nothing more. A row of figures beside every scope name is the
    // information fatigue the client rejected in the first place.
    expect(screen.getByRole('tab', { name: 'Townhouse' })).toHaveTextContent(/^Townhouse$/);
    expect(screen.queryByText('RM 235,000.00')).not.toBeInTheDocument();
    expect(screen.queryByText('RM 18,420.50')).not.toBeInTheDocument();
  });

  it('answers for THAT tab only when its $ is pressed', () => {
    renderTabs();

    fireEvent.click(screen.getByRole('button', { name: 'Show the value of Guard house' }));

    // Its own figure, decimal-exact and formatted by the repo's money helper.
    expect(screen.getByText('RM 18,420.50')).toBeInTheDocument();
    // And nobody else's: one $ reveals one scope, which is the difference from the old
    // strip-wide toggle.
    expect(screen.queryByText('RM 235,000.00')).not.toBeInTheDocument();
  });

  it('gives every tab its own $, named after the scope it answers for', () => {
    renderTabs();

    expect(screen.getByRole('button', { name: 'Show the value of Townhouse' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Show the value of Guard house' }),
    ).toBeInTheDocument();
  });

  it('switches scope when a tab is clicked', () => {
    const { onSelect } = renderTabs();

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Guard house' }));
    expect(onSelect).toHaveBeenCalledWith('s2');
  });
});
