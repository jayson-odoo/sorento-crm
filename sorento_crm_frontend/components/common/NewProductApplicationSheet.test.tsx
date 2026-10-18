/**
 * NEW-PRODUCT-APP v4 paper sheet (AC-NPA-79). The sheet is controlled: `value` is the form
 * state, `onChange` hands back the next one. Assumed props (the coder matches them):
 *   value: FormState, onChange(next), applicationNo?, createdAt?, salesPerson?, readOnly?,
 *   stockInquiryField?: ReactNode, customerField?: ReactNode, brands: LookupFetcher,
 *   errors?: Record<string,string>, lineFooter?: (line, index) => ReactNode,
 *   feedback?: { editable: boolean; onSave?: () => void; saving?: boolean }.
 * DraftLine gains id?, dimension, material, thickness, packing, images[], staged_images: File[].
 */
import React, { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import {
  EMPTY_FORM,
  blankLine,
  type FormState,
} from '@/lib/new-product-application-form';
import { NewProductApplicationSheet } from '@/components/common/NewProductApplicationSheet';

const ORDER = [
  'NEW PRODUCT APPLICATION',
  'REFF:',
  'DATE:',
  'SALES PERSON:',
  'STOCK INQUIRY:',
  'Product 1 of 2',
  'PRODUCT CODE:',
  'PRODUCT TYPE:',
  'DIMENSION:',
  'MATERIAL:',
  'THICKNESS:',
  'PACKING',
  'BRAND:',
  'IMAGE:',
  'QTY:',
  'CUSTOMER:',
  'PROJECT:',
  'TARGET DELIVERY:',
  'REMARK:',
  'PURCHASING FEEDBACK',
  'COST:',
  'LEADTIME:',
];

function Harness({
  initial,
  onState,
  feedback,
  readOnly,
}: {
  initial: FormState;
  onState?: (s: FormState) => void;
  feedback?: { editable: boolean; onSave?: () => void };
  readOnly?: boolean;
}) {
  const [value, setValue] = useState(initial);
  return (
    <NewProductApplicationSheet
      value={value}
      onChange={(s: FormState) => {
        setValue(s);
        onState?.(s);
      }}
      applicationNo="NPA-000001"
      createdAt="2026-10-17T01:00:00"
      salesPerson="Example Staff"
      readOnly={readOnly}
      stockInquiryField={<span>SI26-0412</span>}
      customerField={<input aria-label="Customer" />}
      brands={async () => []}
      feedback={feedback}
    />
  );
}

const two = (): FormState => ({
  ...EMPTY_FORM,
  lines: [blankLine(), blankLine()],
});

describe('paper labels', () => {
  it('renders the paper labels in the paper order, REFF = the application number', () => {
    const { container } = render(<Harness initial={two()} />);
    const text = container.textContent ?? '';
    let at = -1;
    for (const label of ORDER) {
      const next = text.indexOf(label, at + 1);
      expect(next, `label ${label} after position ${at}`).toBeGreaterThan(at);
      at = next;
    }
    expect(screen.getByText('Product 2 of 2')).toBeInTheDocument();
    expect(screen.getByText('NPA-000001')).toBeInTheDocument();
    expect(screen.getByText('Example Staff')).toBeInTheDocument();
  });

  it('marks PRODUCT TYPE required and PACKING has no colon', () => {
    render(<Harness initial={two()} />);
    const type = screen.getAllByText(/PRODUCT TYPE:/)[0];
    expect(type.textContent).toMatch(/\*/);
    expect(screen.getAllByText(/^PACKING$/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/PACKING:/)).toBeNull();
  });

  it('has no item group, base UOM, selling price or supplier inputs', () => {
    render(<Harness initial={two()} />);
    expect(screen.queryByLabelText(/item group/i)).toBeNull();
    expect(screen.queryByLabelText(/base uom/i)).toBeNull();
    expect(screen.queryByLabelText(/selling/i)).toBeNull();
    expect(screen.queryByLabelText(/supplier/i)).toBeNull();
  });
});

describe('products', () => {
  it('+ Add product adds a block and Remove removes one', () => {
    render(<Harness initial={{ ...EMPTY_FORM, lines: [blankLine()] }} />);
    expect(screen.getByText('Product 1 of 1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    expect(screen.getByText('Product 1 of 2')).toBeInTheDocument();
    expect(screen.getByText('Product 2 of 2')).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: /^remove$/i })[0]);
    expect(screen.getByText('Product 1 of 1')).toBeInTheDocument();
    expect(screen.queryByText('Product 2 of 2')).toBeNull();
  });

  it('types into the paper fields of a product', () => {
    const seen: FormState[] = [];
    render(<Harness initial={two()} onState={(s) => seen.push(s)} />);
    fireEvent.change(screen.getAllByLabelText('Product type')[1], {
      target: { value: 'Example sink' },
    });
    fireEvent.change(screen.getAllByLabelText('Dimension')[1], {
      target: { value: '600x400' },
    });
    fireEvent.change(screen.getAllByLabelText('Packing')[1], {
      target: { value: 'Carton' },
    });
    const last = seen.at(-1)!;
    expect(last.lines[1]).toMatchObject({
      description: 'Example sink',
      dimension: '600x400',
      packing: 'Carton',
    });
    expect(last.lines[0].description).toBe('');
  });
});

describe('purchasing feedback', () => {
  const withFeedback = (): FormState => ({
    ...EMPTY_FORM,
    lead_time: '',
    lines: [{ ...blankLine(), id: 'l-1', cost_price: '' }],
  });

  it('is read-only to the applicant: no COST or LEADTIME input, a waiting line', () => {
    render(<Harness initial={withFeedback()} feedback={{ editable: false }} />);
    expect(screen.queryByLabelText('Cost')).toBeNull();
    expect(screen.queryByLabelText('Lead time')).toBeNull();
    expect(
      screen.getByText('Purchasing fills this after approval.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /save feedback/i })).toBeNull();
  });

  it('shows the figures read-only once purchasing has filled them', () => {
    const filled = {
      ...withFeedback(),
      lead_time: '3 weeks',
      lines: [{ ...blankLine(), id: 'l-1', cost_price: '12.50' }],
    };
    render(<Harness initial={filled} feedback={{ editable: false }} />);
    expect(screen.getByText('3 weeks')).toBeInTheDocument();
    expect(screen.getByText(/12\.50/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Cost')).toBeNull();
    expect(
      screen.queryByText('Purchasing fills this after approval.'),
    ).toBeNull();
  });

  it('is editable in place with Save feedback when the host says so', () => {
    const onSave = vi.fn();
    render(
      <Harness
        initial={withFeedback()}
        feedback={{ editable: true, onSave }}
      />,
    );
    fireEvent.change(screen.getByLabelText('Lead time'), {
      target: { value: '3 weeks' },
    });
    fireEvent.change(screen.getByLabelText('Cost'), {
      target: { value: '12.50' },
    });
    expect((screen.getByLabelText('Cost') as HTMLInputElement).value).toBe(
      '12.50',
    );
    fireEvent.click(screen.getByRole('button', { name: /save feedback/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });
});

describe('images', () => {
  it('lists the product images by file name in the IMAGE row', () => {
    const line = {
      ...blankLine(),
      id: 'l-1',
      images: [
        {
          link_id: 'k-1',
          attachment_id: 'at-1',
          filename: 'sample-front.png',
          url: '/files/1',
          content_type: 'image/png',
        },
      ],
    };
    render(<Harness initial={{ ...EMPTY_FORM, lines: [line] }} />);
    expect(screen.getByText('sample-front.png')).toBeInTheDocument();
  });

  it('stages a picked file on the product and lists its name', () => {
    const seen: FormState[] = [];
    render(
      <Harness
        initial={{ ...EMPTY_FORM, lines: [blankLine()] }}
        onState={(s) => seen.push(s)}
      />,
    );
    const file = new File(['x'], 'staged-photo.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('Add image'), {
      target: { files: [file] },
    });
    expect(seen.at(-1)!.lines[0].staged_images).toEqual([file]);
    expect(screen.getByText('staged-photo.png')).toBeInTheDocument();
  });

  it('read-only hides Add image', () => {
    render(
      <Harness
        initial={{ ...EMPTY_FORM, lines: [blankLine()] }}
        readOnly
      />,
    );
    expect(screen.queryByLabelText('Add image')).toBeNull();
    expect(screen.queryByRole('button', { name: /add product/i })).toBeNull();
  });
});
