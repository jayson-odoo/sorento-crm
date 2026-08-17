/**
 * S2 - ClashWarningPanel (AC-C6, AC-C6a, AC-C7).
 *
 * The panel's job is to keep two outcomes visually and textually distinct: a match
 * that STOPS the registration, and a match that is merely worth reading. Collapsing
 * them is what teaches users to dismiss the warning, at which point the blocking case
 * stops working too -- so the separation is the thing under test, not the styling.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ClashWarningPanel } from './ClashWarningPanel';
import type { ClashCandidate } from '../../_shared/types/project.types';

function candidate(overrides: Partial<ClashCandidate> = {}): ClashCandidate {
  return {
    project_id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Setia Alam Phase 3B',
    outcome: 'open',
    status_label: 'Registered',
    owner_user_id: 'u1',
    owner_name: 'Ali',
    developer_name: 'SP Setia',
    estimated_sales_value: '850000.00',
    brands: ['Sorento'],
    last_activity_at: null,
    similarity: 0.86,
    blocks: true,
    ...overrides,
  };
}

describe('ClashWarningPanel', () => {
  it('renders nothing when there is nothing to say', () => {
    const { container } = render(<ClashWarningPanel candidates={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows a loading line only while the first check is in flight', () => {
    render(<ClashWarningPanel candidates={[]} isLoading />);
    expect(screen.getByText(/Checking for existing projects/i)).toBeInTheDocument();
  });

  it('keeps the previous answer on screen while the next check loads', () => {
    // Otherwise the panel flickers empty between keystrokes and the user reads that
    // as "the clash went away".
    render(<ClashWarningPanel candidates={[candidate()]} isLoading />);
    expect(screen.queryByText(/Checking for existing projects/i)).not.toBeInTheDocument();
    expect(screen.getByText('PRJ-000001')).toBeInTheDocument();
  });

  it('renders the incumbent with the facts needed to judge it (AC-C6a)', () => {
    render(<ClashWarningPanel candidates={[candidate()]} />);
    expect(screen.getByText(/Already registered to someone else/i)).toBeInTheDocument();
    expect(screen.getByText('PRJ-000001')).toBeInTheDocument();
    expect(screen.getByText('Ali')).toBeInTheDocument();
    expect(screen.getByText('SP Setia')).toBeInTheDocument();
    expect(screen.getByText('Registered')).toBeInTheDocument();
    expect(screen.getByText('RM 850,000')).toBeInTheDocument();
    expect(screen.getByText('Sorento')).toBeInTheDocument();
  });

  it('separates a blocking match from a context match', () => {
    render(
      <ClashWarningPanel
        candidates={[
          candidate(),
          candidate({ project_id: 'p2', project_code: 'PRJ-000002', blocks: false }),
        ]}
      />,
    );
    expect(screen.getByText(/Already registered to someone else/i)).toBeInTheDocument();
    expect(screen.getByText(/Similar projects/i)).toBeInTheDocument();
  });

  it('offers a way out only on a blocking match (AC-C7)', () => {
    // A context match needs no recourse -- the user can just save -- and offering
    // "Ask to join" there would imply they are blocked when they are not.
    const onRequestJoin = vi.fn();
    const onDispute = vi.fn();
    render(
      <ClashWarningPanel
        candidates={[candidate({ blocks: false })]}
        onRequestJoin={onRequestJoin}
        onDispute={onDispute}
      />,
    );
    expect(screen.queryByRole('button', { name: /Ask to join/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Dispute/i })).not.toBeInTheDocument();
  });

  it('routes the blocked user to the owner or a manager', () => {
    const onRequestJoin = vi.fn();
    const onDispute = vi.fn();
    const blocking = candidate();
    render(
      <ClashWarningPanel
        candidates={[blocking]}
        onRequestJoin={onRequestJoin}
        onDispute={onDispute}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Ask to join/i }));
    expect(onRequestJoin).toHaveBeenCalledWith(blocking);
    fireEvent.click(screen.getByRole('button', { name: /Dispute/i }));
    expect(onDispute).toHaveBeenCalledWith(blocking);
  });

  it('marks a lost incumbent so a re-tender does not look like a live conflict', () => {
    // A lost project is a perfect title match that must NOT block (AC-C6), so the
    // outcome has to be visible or the context row reads as an unexplained warning.
    render(
      <ClashWarningPanel candidates={[candidate({ blocks: false, outcome: 'lost' })]} />,
    );
    expect(screen.getByText('lost')).toBeInTheDocument();
  });

  it('omits facts it does not have rather than printing empty labels', () => {
    render(
      <ClashWarningPanel
        candidates={[
          candidate({
            blocks: false,
            developer_name: null,
            estimated_sales_value: null,
            status_label: null,
            brands: [],
          }),
        ]}
      />,
    );
    expect(screen.queryByText('Developer:')).not.toBeInTheDocument();
    expect(screen.queryByText('Estimated:')).not.toBeInTheDocument();
    expect(screen.queryByText('Stage:')).not.toBeInTheDocument();
  });
});

describe('a block raised because the developer is still unstated', () => {
  /**
   * Leaving Developer blank used to skip the exclusivity check entirely (the clash search
   * was filtered on the value given, so a blank one compared against nothing). It blocks
   * now, which means the panel has to name the cheapest way out: say who the developer is.
   * Offering only "ask to join" would send someone to a manager over a field they simply
   * had not filled in yet.
   */
  it('tells the user to name their developer when none is chosen', () => {
    render(<ClashWarningPanel candidates={[candidate()]} developerChosen={false} />);

    expect(screen.getByText(/Name the developer below/i)).toBeInTheDocument();
  });

  it('drops that advice once a developer is named, leaving join and dispute', () => {
    render(<ClashWarningPanel candidates={[candidate()]} developerChosen />);

    expect(screen.queryByText(/Name the developer below/i)).toBeNull();
    expect(screen.getByText(/raise a dispute/i)).toBeInTheDocument();
  });
});
