/**
 * ClashWarningPanel (PROJECT-REGISTER-V2 D2, D3).
 *
 * One line per candidate. A match that STOPS the registration and a match that is merely
 * worth reading stay textually distinct ("Project already registered:" vs "Similar project:"),
 * because collapsing them teaches users to dismiss the warning, at which point the blocking
 * case stops working too. The panel carries no owner, stage, similarity or row buttons: the
 * form's one primary ("Register interest in <code>") is the way out.
 */
import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
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

  it('renders a blocking match as one line: label, code linking to the project, title', () => {
    render(<ClashWarningPanel candidates={[candidate()]} />);
    expect(screen.getByText('Project already registered:')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'PRJ-000001' })).toHaveAttribute(
      'href',
      '/project-sales/p1',
    );
    expect(screen.getByText('Setia Alam Phase 3B')).toHaveAttribute('title', 'Setia Alam Phase 3B');
  });

  it('carries no owner, developer, stage, value or similarity facts', () => {
    render(<ClashWarningPanel candidates={[candidate()]} />);
    for (const fact of ['Ali', 'SP Setia', 'Registered', 'RM 850,000']) {
      expect(screen.queryByText(fact)).not.toBeInTheDocument();
    }
    expect(screen.queryByText(/Already registered to someone else/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/% match|similar to/i)).not.toBeInTheDocument();
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
    expect(screen.getByText('Project already registered:')).toBeInTheDocument();
    expect(screen.getByText('Similar project:')).toBeInTheDocument();
  });

  it('has no row buttons at all, on a blocking or a context match', () => {
    // The form's footer primary ("Register interest in <code>") is the only action.
    render(
      <ClashWarningPanel
        candidates={[candidate(), candidate({ project_id: 'p2', blocks: false })]}
      />,
    );
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryByText('Blocked by an existing project')).not.toBeInTheDocument();
  });

  it('marks a lost incumbent so a re-tender does not look like a live conflict', () => {
    // A lost project is a perfect title match that must NOT block, so the outcome has to
    // be visible or the context row reads as an unexplained warning.
    render(
      <ClashWarningPanel candidates={[candidate({ blocks: false, outcome: 'lost' })]} />,
    );
    expect(screen.getByText('lost')).toBeInTheDocument();
  });
});
