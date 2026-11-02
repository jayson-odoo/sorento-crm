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
});
