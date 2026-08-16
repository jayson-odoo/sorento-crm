/**
 * The one rendering every import dialog uses to report what a Test found.
 *
 * The claim worth a test file of its own is the SKIP CLAIM. Four dialogs used to render this
 * themselves and they disagreed about whether a warning means rows are being dropped: the
 * customer importer once told an operator "3 rows need a look, those rows are skipped" about
 * a clean 900-row file that happened to carry three unrecognised columns. So:
 *
 * - a caller that HAS a real skip count gets the skip wording, with that count;
 * - a caller that does not gets a heading which claims nothing;
 * - warnings never claim a skip, whatever they say.
 *
 * The rest is the shape: sections appear only when they have something to say (a report, not
 * a form - an empty "0 warnings" panel is noise), and a long list is capped with a toggle.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ImportFeedbackSections } from './ImportFeedbackSections';

describe('ImportFeedbackSections - the skip claim', () => {
  it('says N rows skipped when the caller has a real skip count', () => {
    render(
      <ImportFeedbackSections
        rejectedRows={[
          { row: 2, reason: 'no customer name' },
          { row: 7, reason: 'no customer name' },
        ]}
        skippedCount={2}
      />,
    );

    expect(screen.getByText('2 rows skipped')).toBeInTheDocument();
    expect(screen.getByText('Row 2')).toBeInTheDocument();
  });

  it('claims nothing about skipping when the caller has no skip count', () => {
    /**
     * The SCM outstanding channel is the case: its row list mixes rows the reader dropped
     * with documents that imported perfectly well and only lack an order type. A skip claim
     * would be wrong for half of it.
     */
    render(
      <ImportFeedbackSections
        rejectedRows={[{ row: 14, reason: 'states no order type', value: 'SO375073' }]}
      />,
    );

    expect(screen.getByText('Rows that need a look (1)')).toBeInTheDocument();
    expect(screen.queryByText(/skipped/i)).toBeNull();
  });

  it('never lets a warning claim rows are skipped', () => {
    render(
      <ImportFeedbackSections
        warnings={[
          'Column not recognised: SALESMAN',
          '2 stock locations we do not recognise: BRW-ZZ, BRW-YY',
        ]}
      />,
    );

    expect(screen.getByText('2 warnings')).toBeInTheDocument();
    expect(screen.queryByText(/rows skipped/i)).toBeNull();
    expect(screen.queryByText(/need a look/i)).toBeNull();
  });

  it('reads "1 row skipped" in the singular', () => {
    render(
      <ImportFeedbackSections rejectedRows={[{ row: 3, reason: 'bad' }]} skippedCount={1} />,
    );

    expect(screen.getByText('1 row skipped')).toBeInTheDocument();
  });
});

describe('ImportFeedbackSections - what each section shows', () => {
  it('renders nothing at all when there is nothing to report', () => {
    const { container } = render(<ImportFeedbackSections />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a blocking error apart from the warnings', () => {
    render(
      <ImportFeedbackSections
        errors={['No order block found in this file.']}
        warnings={['534 charge lines carry cost but no product']}
      />,
    );

    expect(screen.getByText('Nothing would be imported.')).toBeInTheDocument();
    expect(screen.getByText('No order block found in this file.')).toBeInTheDocument();
    expect(screen.getByText('1 warning')).toBeInTheDocument();
  });

  it('names each unrecognised column as its own chip', () => {
    render(<ImportFeedbackSections unrecognisedColumns={['SALESMAN', 'CREDIT TERM']} />);

    expect(screen.getByText('Columns we did not recognise (2)')).toBeInTheDocument();
    expect(screen.getByText('SALESMAN')).toBeInTheDocument();
    expect(screen.getByText('CREDIT TERM')).toBeInTheDocument();
  });

  it('caps a long row list and expands it on request', () => {
    render(
      <ImportFeedbackSections
        rejectedRows={Array.from({ length: 11 }, (_, i) => ({
          row: i + 2,
          reason: 'no customer name',
        }))}
        skippedCount={11}
      />,
    );

    expect(screen.getByText('Row 2')).toBeInTheDocument();
    expect(screen.queryByText('Row 12')).toBeNull();

    fireEvent.click(screen.getByText('Show all 11'));
    expect(screen.getByText('Row 12')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Show less'));
    expect(screen.queryByText('Row 12')).toBeNull();
  });

  it('renders a row with no row number without inventing one', () => {
    // A closure or a withdrawal is reached by ABSENCE - there is no source row to point at.
    render(
      <ImportFeedbackSections
        rejectedRows={[{ row: null, reason: 'the document names two different agents' }]}
      />,
    );

    expect(screen.getByText('the document names two different agents')).toBeInTheDocument();
    expect(screen.queryByText(/^Row /)).toBeNull();
  });
});

describe('ImportFeedbackSections - notices', () => {
  const AGENTS = {
    key: 'agents',
    title: 'Agents with no demand class',
    items: [
      { key: 'SEAN III', code: 'SEAN III', text: 'new agent, unclassified' },
      { key: 'LCL', code: 'LCL', text: 'this agent carries no demand class' },
    ],
    hint: 'Their orders are imported.',
  };

  it('renders a notice section beside the standard ones, with its own count', () => {
    render(<ImportFeedbackSections notices={[AGENTS]} />);

    expect(screen.getByText('Agents with no demand class (2)')).toBeInTheDocument();
    expect(screen.getByText('SEAN III')).toBeInTheDocument();
    expect(screen.getByText('new agent, unclassified')).toBeInTheDocument();
    expect(screen.getByText('Their orders are imported.')).toBeInTheDocument();
  });

  it('renders no section for an empty notice', () => {
    render(<ImportFeedbackSections notices={[{ ...AGENTS, items: [] }]} />);

    expect(screen.queryByText(/Agents with no demand class/)).toBeNull();
  });

  it('never mixes a notice into the rejected rows', () => {
    // Nothing was skipped by an unclassified agent, so it must not appear under a heading
    // that says rows were.
    render(
      <ImportFeedbackSections
        rejectedRows={[{ row: 2, reason: 'no item code' }]}
        skippedCount={1}
        notices={[AGENTS]}
      />,
    );

    const skipped = screen.getByText('1 row skipped').closest('div') as HTMLElement;
    expect(skipped.textContent).not.toContain('SEAN III');
  });
});
