/**
 * P6 section 9.7a - free-text notes the extractor found but did not interpret.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DeliveryScheduleNotes } from './DeliveryScheduleNotes';

describe('DeliveryScheduleNotes', () => {
  it('names the page and quotes the note verbatim', () => {
    render(
      <DeliveryScheduleNotes
        notes={[
          {
            page_no: 7,
            text: 'ONLY FOR FLOOR TRAP TO BE DELIVER IN 2026, START FROM 23/7/2026',
          },
        ]}
      />,
    );

    expect(screen.getByText('Notes on the document')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Page 7: ONLY FOR FLOOR TRAP TO BE DELIVER IN 2026, START FROM 23/7/2026',
      ),
    ).toBeInTheDocument();
  });

  it('lists every note, one line each', () => {
    render(
      <DeliveryScheduleNotes
        notes={[
          { page_no: 3, text: 'First remark.' },
          { page_no: 7, text: 'Second remark.' },
        ]}
      />,
    );

    expect(screen.getByText('Page 3: First remark.')).toBeInTheDocument();
    expect(screen.getByText('Page 7: Second remark.')).toBeInTheDocument();
  });

  it('keeps the header and says so plainly when there are none - never hides the section', () => {
    render(<DeliveryScheduleNotes notes={[]} />);

    expect(screen.getByText('Notes on the document')).toBeInTheDocument();
    expect(screen.getByText('No notes on the document')).toBeInTheDocument();
  });
});
