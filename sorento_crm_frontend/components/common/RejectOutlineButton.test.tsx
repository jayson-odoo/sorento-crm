/** One Reject button for the stock inquiry and the new product application (owner 8 Nov, crew pass 3). */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { RejectOutlineButton } from './RejectOutlineButton';

describe('RejectOutlineButton', () => {
  it('is the stock inquiry Reject: outline, small, lighter red border, XCircle', () => {
    const onClick = vi.fn();
    render(<RejectOutlineButton onClick={onClick} data-guide-target="x.reject" />);
    const btn = screen.getByRole('button', { name: 'Reject' });
    expect(btn.className).toMatch(/border-destructive\/40/);
    expect(btn.className).toMatch(/text-destructive/);
    expect(btn.className).toMatch(/hover:bg-destructive\/10/);
    expect(btn.getAttribute('data-guide-target')).toBe('x.reject');
    expect(btn.querySelector('svg')).not.toBeNull();
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalled();
  });
});
