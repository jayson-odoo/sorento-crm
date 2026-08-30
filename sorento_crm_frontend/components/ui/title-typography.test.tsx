/**
 * S2-03 (titles ride the baked type scale) and S2-07 (card shadow tint renders).
 * See documentation/plans/design-system/apple-alignment-acceptance-criteria.md
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { AlertDialog, AlertDialogContent, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Card, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';

describe('S2-03 titles use the baked type scale', () => {
  it('gives CardTitle leading-tight tracking-normal', () => {
    render(<CardTitle>Order summary</CardTitle>);
    const title = screen.getByText('Order summary');
    expect(title.className).toContain('leading-tight');
    expect(title.className).toContain('tracking-normal');
    expect(title.className).not.toContain('leading-none');
    expect(title.className).not.toContain('tracking-tight');
  });

  it('gives DialogTitle leading-tight tracking-normal', () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Edit product</DialogTitle>
        </DialogContent>
      </Dialog>,
    );
    const title = screen.getByText('Edit product');
    expect(title.className).toContain('leading-tight');
    expect(title.className).toContain('tracking-normal');
    expect(title.className).not.toContain('leading-none');
    expect(title.className).not.toContain('tracking-tight');
  });

  it('gives AlertDialogTitle leading-tight tracking-normal', () => {
    render(
      <AlertDialog open>
        <AlertDialogContent>
          <AlertDialogTitle>Delete order</AlertDialogTitle>
        </AlertDialogContent>
      </AlertDialog>,
    );
    const title = screen.getByText('Delete order');
    expect(title.className).toContain('leading-tight');
    expect(title.className).toContain('tracking-normal');
  });
});

describe('S2-07 card shadow tint', () => {
  it('renders shadow-black/5 rather than a stray black/5', () => {
    render(<Card data-testid="card" />);
    const card = screen.getByTestId('card');
    expect(card.className).toContain('shadow-black/5');
    expect(card.className).not.toMatch(/(^|\s)black\/5(\s|$)/);
  });
});
