/**
 * The per-entry action slot on the shared timeline (round 6, 6.3).
 *
 * The office mounts export buttons in it; the contact portal passes nothing and
 * must be untouched by its existence, which is the second case below.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RevisionTimeline, type FormRevisionEntry } from './RevisionTimeline';

function entry(overrides: Partial<FormRevisionEntry> = {}): FormRevisionEntry {
  return {
    id: 'rev-0',
    version_no: 0,
    revision_no: 0,
    kind: 'original',
    label: 'Original',
    reason: null,
    submitted_at: '2026-07-01T02:00:00',
    submitted_by: 'Alex Tan',
    snapshot: {},
    attachments: [],
    changes: [],
    snapshot_fields: null,
    ...overrides,
  };
}

const entries = [
  entry(),
  entry({ id: 'rev-1', version_no: 1, revision_no: 1, kind: 'revision', label: 'Revision 1' }),
];

describe('RevisionTimeline entryActions', () => {
  it('renders the caller-supplied actions for every entry', () => {
    render(
      <RevisionTimeline
        entries={entries}
        entryActions={(e) => <button type="button">Export {e.label}</button>}
      />,
    );
    expect(screen.getByRole('button', { name: 'Export Original' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export Revision 1' })).toBeInTheDocument();
  });

  it('renders nothing extra without the prop, so the portal is unaffected', () => {
    render(<RevisionTimeline entries={entries} />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('keeps the full-form button beside the actions', () => {
    render(
      <RevisionTimeline
        entries={[
          entry({
            snapshot_fields: [{ field: 'quantity', label: 'Quantity', value: '10' }],
          }),
        ]}
        entryActions={() => <button type="button">Export</button>}
      />,
    );
    expect(screen.getByTestId('revision-view-form')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });
});
