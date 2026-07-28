import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import ComplaintNotifiableFieldDialog from './ComplaintNotifiableFieldDialog';

const OPTIONS = [
  { id: 'rc-1', name: 'Installation error' },
  { id: 'rc-2', name: 'Manufacturing defect' },
];

// Typed via vi.fn's implementation so the mocks satisfy the component's prop
// signatures under tsc, not just at runtime under vitest.
let onUpdate: ReturnType<typeof makeOnUpdate>;
let onUpdateAndReply: ReturnType<typeof makeOnUpdateAndReply>;
let onOpenChange: ReturnType<typeof makeOnOpenChange>;

const makeOnUpdate = () => vi.fn(async (_id: string | null): Promise<unknown> => undefined);
const makeOnUpdateAndReply = () => vi.fn(async (_id: string): Promise<unknown> => undefined);
const makeOnOpenChange = () => vi.fn((_open: boolean): void => undefined);

function renderDialog(
  props: Partial<React.ComponentProps<typeof ComplaintNotifiableFieldDialog>> = {},
) {
  return render(
    <ComplaintNotifiableFieldDialog
      open
      onOpenChange={onOpenChange}
      kind="root_cause"
      value="rc-1"
      options={OPTIONS}
      onUpdate={onUpdate}
      onUpdateAndReply={onUpdateAndReply}
      canReply
      {...props}
    />,
  );
}

beforeEach(() => {
  onUpdate = makeOnUpdate();
  onUpdateAndReply = makeOnUpdateAndReply();
  onOpenChange = makeOnOpenChange();
});

describe('ComplaintNotifiableFieldDialog', () => {
  it('renders the root cause copy with Cancel / Update / Update & Reply', () => {
    renderDialog();
    expect(screen.getByText('Edit root cause')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Update' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Update & Reply/ })).toBeInTheDocument();
    // Trigger label resolves the FK to the human-readable name (no UUIDs in the UI).
    expect(screen.getByText('Installation error')).toBeInTheDocument();
  });

  it('renders the resolution copy for kind="resolution"', () => {
    renderDialog({ kind: 'resolution', value: null });
    expect(screen.getByText('Edit resolution')).toBeInTheDocument();
  });

  it('Update saves the seeded value and closes', async () => {
    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith('rc-1'));
    expect(onUpdateAndReply).not.toHaveBeenCalled();
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('Update & Reply saves then notifies the contact', async () => {
    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: /Update & Reply/ }));
    await waitFor(() => expect(onUpdateAndReply).toHaveBeenCalledWith('rc-1'));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('disables Update & Reply when no value is selected (nothing to tell the contact)', () => {
    renderDialog({ value: null });
    expect(screen.getByRole('button', { name: /Update & Reply/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Update' })).not.toBeDisabled();
  });

  it('hides Update & Reply when the complaint has no Respond.io conversation', () => {
    renderDialog({ canReply: false });
    expect(screen.queryByRole('button', { name: /Update & Reply/ })).toBeNull();
  });

  it('Cancel closes without saving', () => {
    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onUpdate).not.toHaveBeenCalled();
    expect(onUpdateAndReply).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('disables every action while a mutation is pending', () => {
    renderDialog({ isPending: true });
    expect(screen.getByRole('button', { name: 'Update' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Update & Reply/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });

  // Mobile rule (UAC-complaint-root-cause-resolution-edit.md B6): every dialog
  // must be scrollable and usable at ~375px - enforced globally by the shared
  // dialogContentVariants (bounded max-h + overflow-y-auto), not per-dialog.
  it('is scrollable at ~375px (shared dialog max-height rule)', () => {
    renderDialog();
    const content = document.querySelector('[data-slot="dialog-content"]');
    expect(content).not.toBeNull();
    expect(content?.className).toMatch(/overflow-y-auto/);
    expect(content?.className).toMatch(/max-h-\[90dvh\]/);
  });
});
