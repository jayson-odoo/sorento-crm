/** PRICETAG-COMBO AC-4.2: the Combo tokens show in Insert field. */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { InsertFieldDialog } from './InsertFieldDialog';

function open(groups?: ('Product' | 'Specs' | 'Set' | 'Line' | 'Combo')[]) {
  const onDone = vi.fn();
  render(
    <InsertFieldDialog
      open
      value=""
      data={null}
      specKeys={[]}
      groups={groups}
      onCancel={vi.fn()}
      onDone={onDone}
    />,
  );
  return onDone;
}

describe('Insert field, Combo group (AC-4.2)', () => {
  it('lists the three combo tokens under a Combo heading and inserts one', () => {
    const onDone = open();
    expect(screen.getByText('Combo')).toBeInTheDocument();
    expect(screen.getByText('{{combo.name}}')).toBeInTheDocument();
    expect(screen.getByText('{{combo.description}}')).toBeInTheDocument();
    expect(screen.getByText('{{combo.free_items}}')).toBeInTheDocument();

    fireEvent.click(screen.getByText('{{combo.free_items}}'));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledWith('{{combo.free_items}}');
  });

  it('offers no Combo group where only Product and Specs are allowed', () => {
    open(['Product', 'Specs']);
    expect(screen.queryByText('{{combo.name}}')).toBeNull();
  });

  it('lists "All parts as a list" and leaves out an omitted path (COMBO-SETTINGS-UX review S6)', () => {
    render(
      <InsertFieldDialog
        open
        value=""
        data={null}
        specKeys={[]}
        groups={['Combo', 'Combo positions']}
        omitPaths={['combo.description']}
        onCancel={vi.fn()}
        onDone={vi.fn()}
      />,
    );
    expect(screen.getByText('{{combo.parts}}')).toBeInTheDocument();
    expect(screen.getByText('{{combo.name}}')).toBeInTheDocument();
    expect(screen.queryByText('{{combo.description}}')).toBeNull();
  });

  it('a part field shows its readable name only, never its raw token (crew F3)', () => {
    render(
      <InsertFieldDialog
        open
        value=""
        data={null}
        specKeys={[]}
        groups={['Combo', 'Parts']}
        extraFields={[
          { path: 'part.0123456789abcdef0123456789abcdef.code', token: '{{part.0123456789abcdef0123456789abcdef.code}}', label: 'BASIN - SRTWB2380: code', group: 'Parts', hideToken: true },
        ]}
        onCancel={vi.fn()}
        onDone={vi.fn()}
      />,
    );
    expect(screen.getByText('BASIN - SRTWB2380: code')).toBeInTheDocument();
    expect(screen.queryByText('{{part.0123456789abcdef0123456789abcdef.code}}')).toBeNull();
    expect(screen.getByText('{{combo.name}}')).toBeInTheDocument();
  });

  it('previews "All parts (one line each)" with real values (crew F2)', () => {
    const data = {
      kind: 'product',
      product: {
        code: 'SRTBF11829',
        slots: {
          main: { product_id: 'h', code: 'SRTBF11829', name: 'C', dimensions: '', dimensions_lwh: 'L780xW480xH400mm' },
          fixed: [{ product_id: 'b', code: 'SRTWB2380', name: 'B', dimensions: '', dimensions_lwh: '' }],
          groups: [],
          upgrades: [],
        },
        combo: { id: 'c', name: 'BF', description: null, free_items: null, choices: [], upgrades: [], main_label: 'CABINET', part_labels: { b: 'BASIN' } },
      },
    };
    render(
      <InsertFieldDialog
        open
        value=""
        data={data as never}
        specKeys={[]}
        groups={['Parts']}
        extraFields={[{ path: 'combo.all_parts', token: '{{combo.all_parts}}', label: 'All parts (one line each)', group: 'Parts', hideToken: true }]}
        onCancel={vi.fn()}
        onDone={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText('All parts (one line each)'));
    expect(screen.getByText(/SRTBF11829 \(CABINET\)/)).toBeInTheDocument();
    expect(screen.getByText(/SRTWB2380 \(BASIN\)/)).toBeInTheDocument();
  });
});
