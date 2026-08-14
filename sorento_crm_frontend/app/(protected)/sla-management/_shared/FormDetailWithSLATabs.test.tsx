/**
 * FormDetailWithSLATabs - the office tab strip shared by all six form detail
 * pages (tickets, complaints, stock inquiries, purchase requests, sponsorship
 * forms).
 *
 * Two things are pinned here. The ORDER (Details, caller-supplied extraTabs,
 * SLA Tracking) is what six pages agree on, so a caller inserting a tab must
 * never be able to land it after SLA Tracking. And the STYLE is the house
 * underlined strip (`variant="line"`, bare lucide icon then a `<span>` label),
 * the same one the product and user detail pages use - one record, one tab
 * look, wherever you are in the system.
 *
 * The extraTab icon is optional: a caller with nothing meaningful to draw gets
 * a label-only trigger rather than filler.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import { Paperclip } from 'lucide-react';

// The SLA tab's own body fetches; this file is about the strip around it.
vi.mock('./FormSLATrackingTab', () => ({
  __esModule: true,
  default: () => <div data-testid="form-sla-tracking-tab" />,
}));

import FormDetailWithSLATabs, { type FormDetailExtraTab } from './FormDetailWithSLATabs';

function renderTabs(extraTabs?: FormDetailExtraTab[]) {
  render(
    <FormDetailWithSLATabs
      sourceEntityType="complaint"
      sourceEntityId="c-1"
      extraTabs={extraTabs}
    >
      <div>Details content</div>
    </FormDetailWithSLATabs>,
  );
}

beforeEach(cleanup);

describe('FormDetailWithSLATabs - tab order', () => {
  it('renders Details then SLA Tracking when the caller supplies no extra tabs', () => {
    renderTabs();

    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Details',
      'SLA Tracking',
    ]);
  });

  it('keeps caller tabs between Details and SLA Tracking, in the order given', () => {
    renderTabs([
      { value: 'fulfilment', label: 'Fulfilment DOs', content: <div>dos</div> },
      { value: 'chat', label: 'Chat records', content: <div>chat</div> },
    ]);

    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Details',
      'Fulfilment DOs',
      'Chat records',
      'SLA Tracking',
    ]);
  });

  it('lands on Details, with the caller content rendered in its panel', () => {
    renderTabs([{ value: 'chat', label: 'Chat records', content: <div>chat body</div> }]);

    expect(screen.getByRole('tab', { name: 'Details' })).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByText('Details content')).toBeInTheDocument();
    expect(screen.queryByText('chat body')).toBeNull();
  });
});

describe('FormDetailWithSLATabs - the house underlined strip', () => {
  it('uses the line variant, not the default grey pill strip', () => {
    renderTabs();

    const list = screen.getByRole('tablist');
    expect(list).toHaveClass('border-b');
    expect(list).not.toHaveClass('bg-accent');
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab).toHaveClass('border-b-2');
    }
  });

  it('gives Details and SLA Tracking their own icons', () => {
    renderTabs();

    for (const name of ['Details', 'SLA Tracking']) {
      expect(
        screen.getByRole('tab', { name }).querySelector('svg'),
      ).not.toBeNull();
    }
  });

  it('renders a caller-supplied icon on its trigger', () => {
    renderTabs([
      {
        value: 'files',
        label: 'Files',
        icon: <Paperclip data-testid="files-tab-icon" />,
        content: <div>files</div>,
      },
    ]);

    const tab = screen.getByRole('tab', { name: 'Files' });
    expect(tab).toHaveTextContent('Files');
    expect(within(tab).getByTestId('files-tab-icon')).toBeInTheDocument();
  });

  it('renders a label-only trigger when the caller supplies no icon', () => {
    renderTabs([{ value: 'files', label: 'Files', content: <div>files</div> }]);

    const tab = screen.getByRole('tab', { name: 'Files' });
    expect(tab).toHaveTextContent('Files');
    expect(tab.querySelector('svg')).toBeNull();
  });
});
