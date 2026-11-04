/** QUOTE-COVER-DESIGN round 2: the A4 preview frame grows with its content (no clipping). */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CoverPagePreview } from './CoverPagePreview';

describe('CoverPagePreview', () => {
  it('a long closing is in the document and the frame is not overflow-hidden with a fixed height', () => {
    const long = Array.from({ length: 80 }, (_, i) => `<p>Closing paragraph ${i}</p>`).join('');
    const { container } = render(
      <CoverPagePreview
        cover={{
          cover_title: 'QUOTATION',
          cover_show_letterhead: true,
          cover_rows: [{ key: 'reference', label: 'Reference No.', text: 'SRT/Q/1-R1' }],
          cover_intro_html: '<p>Intro</p>',
          cover_closing_html: long,
          sender_name: 'Sorento Sdn Bhd',
          sender_logo_url: null,
        } as never}
      />,
    );
    expect(screen.getByText('Closing paragraph 79')).toBeInTheDocument();
    expect(container.querySelector('.overflow-hidden')).toBeNull();
    const fixed = Array.from(container.querySelectorAll<HTMLElement>('[style]')).filter(
      (el) => /(^|;|\s)height:\s*\d/.test(el.getAttribute('style') ?? ''),
    );
    expect(fixed).toHaveLength(0);
  });
});
