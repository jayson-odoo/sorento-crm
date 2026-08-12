/**
 * S21 - the quotation line's product photograph, and the four things it can say.
 *
 * The empty state is the point of this file. Only 30 of the 535 products with candidate
 * photographs carry a choice, so on day one this cell is far more often "nobody has answered"
 * than a picture - and if that reads as a broken image, or as a blank cell somebody has to
 * interpret, the feature is worse than not having it.
 *
 * Four states, three different problems, three different words:
 *
 * - `not_chosen`  photographs exist, nobody has said which. ONE CLICK away, so it links.
 * - `no_photos`   nothing to choose between. The answer is an upload, not a click.
 * - `off_catalog` no product at all, so no flag could ever point at anything. Never an invitation.
 * - a staged row  the server has not decided yet, so the cell claims nothing.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { QuotationLine } from '../../_shared/types/project.types';
import { QuotationLinePhoto, productPhotoHref } from './QuotationLinePhoto';

function line(overrides: Partial<QuotationLine> = {}): QuotationLine {
  return {
    id: 'line-1',
    version_id: 'version-1',
    product_id: 'product-1',
    product_code: 'CWC604-RL',
    unit_price: '250.00',
    quantity: '4',
    line_total: '1000.00',
    is_non_standard: false,
    is_below_floor: false,
    sort_order: 0,
    ...overrides,
  };
}

describe('QuotationLinePhoto', () => {
  it('shows the chosen photograph, named by the file it came from', () => {
    render(
      <QuotationLinePhoto
        line={line({
          product_image: {
            state: 'chosen',
            url: 'https://cdn.test/signed/wc.jpg?sig=1',
            filename: 'CWC604-RL front.jpg',
            candidate_count: 3,
          },
        })}
      />,
    );

    const picture = screen.getByRole('img');
    expect(picture).toHaveAttribute('src', 'https://cdn.test/signed/wc.jpg?sig=1');
    // The filename on hover, not on the page: it is provenance, and a quotation line is already
    // carrying a description, a code and a price.
    expect(picture).toHaveAttribute('title', 'CWC604-RL front.jpg');
    expect(picture.getAttribute('alt')).toContain('CWC604-RL');
  });

  it('says nobody has chosen yet, and links to where the choice is made', () => {
    render(
      <QuotationLinePhoto
        line={line({
          product_image: { state: 'not_chosen', url: null, filename: null, candidate_count: 3 },
        })}
      />,
    );

    expect(screen.getByText('No photo chosen')).toBeInTheDocument();
    // How much work it would be: three photographs is a click, not a photo shoot.
    expect(screen.getByText('3 photos')).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', productPhotoHref('product-1'));
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('singularises the one candidate rather than saying "1 photos"', () => {
    render(
      <QuotationLinePhoto
        line={line({
          product_image: { state: 'not_chosen', url: null, filename: null, candidate_count: 1 },
        })}
      />,
    );
    expect(screen.getByText('1 photo')).toBeInTheDocument();
  });

  it('distinguishes a product with NO photograph from one nobody has chosen for', () => {
    render(
      <QuotationLinePhoto
        line={line({
          product_image: { state: 'no_photos', url: null, filename: null, candidate_count: 0 },
        })}
      />,
    );

    // Different problem, different words: this one needs a photo shoot, not a click. The link is
    // still there, because uploading one starts on the same tab.
    expect(screen.getByText('No photo on file')).toBeInTheDocument();
    expect(screen.queryByText(/photos?$/)).not.toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', productPhotoHref('product-1'));
  });

  it('never invites a choice on an off-catalog line', () => {
    render(
      <QuotationLinePhoto
        line={line({
          product_id: null,
          product_code: null,
          product_image: {
            state: 'off_catalog',
            url: null,
            filename: null,
            candidate_count: 0,
          },
        })}
      />,
    );

    // There is no product, so there is no `product_attachments` row a flag could point at. A
    // "choose a photo" link here would lead nowhere and would imply a second place a picture gets
    // decided, which is exactly the defect the single flag removes.
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByText(/no photo/i)).not.toBeInTheDocument();
  });

  it('claims nothing for a row staged in this edit session', () => {
    const { container } = render(<QuotationLinePhoto line={null} />);
    // Not "no photo chosen": the server has not resolved anything for a row it has never seen,
    // and saying so would be a claim we cannot support. Same rule the row's other server-decided
    // facts (Off-catalog, Below floor, Non-standard) already follow.
    expect(container).toBeEmptyDOMElement();
  });

  it('states an unreachable picture without pretending it is a choice to make', () => {
    render(
      <QuotationLinePhoto
        line={line({
          product_image: { state: 'chosen', url: null, filename: 'wc.jpg', candidate_count: 0 },
        })}
      />,
    );

    // Storage being down is not something the salesperson fixes by choosing again.
    expect(screen.getByText('Photo unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('falls back to the off-catalog dash on a payload from before S21', () => {
    const { container } = render(<QuotationLinePhoto line={line()} />);
    expect(container.textContent).toBe('-');
  });

  it('opens the viewer on the line that was clicked', () => {
    // The cell is the only way into the viewer, so it has to be a real control: reachable by
    // keyboard, named for the product rather than "button", and it must not also put the row
    // into edit mode on the way past.
    const onPreview = vi.fn();
    render(
      <QuotationLinePhoto
        line={line({
          product_image: {
            state: 'chosen',
            url: 'https://cdn.test/thumb.jpg',
            preview_url: 'https://cdn.test/original.jpg',
            attachment_id: 'attachment-1',
            filename: 'CWC604-RL.jpg',
            candidate_count: 3,
          },
        })}
        onPreview={onPreview}
      />,
    );

    const button = screen.getByRole('button', { name: 'Preview CWC604-RL photo' });
    fireEvent.click(button);
    expect(onPreview).toHaveBeenCalledTimes(1);
  });

  it('stays a plain picture where there is no viewer to open', () => {
    // The printed/read-only renders pass no handler. A button that does nothing when pressed
    // is worse than a picture, because it advertises an action.
    render(
      <QuotationLinePhoto
        line={line({
          product_image: {
            state: 'chosen',
            url: 'https://cdn.test/thumb.jpg',
            preview_url: 'https://cdn.test/original.jpg',
            attachment_id: 'attachment-1',
            filename: 'CWC604-RL.jpg',
            candidate_count: 3,
          },
        })}
      />,
    );

    expect(screen.getByRole('img')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
