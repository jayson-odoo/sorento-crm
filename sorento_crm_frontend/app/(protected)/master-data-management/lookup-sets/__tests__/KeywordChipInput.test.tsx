import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import KeywordChipInput from '../components/KeywordChipInput';

describe('KeywordChipInput', () => {
  it('adds chip on Enter', () => {
    const onChange = vi.fn();
    render(<KeywordChipInput value={[]} onChange={onChange} />);
    const input = screen.getByPlaceholderText('Add keyword and press Enter');
    fireEvent.change(input, { target: { value: 'urgent' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith([{ keyword: 'urgent', locale: null }]);
  });

  it('removes chip on click', () => {
    const onChange = vi.fn();
    render(<KeywordChipInput value={[{ keyword: 'a', locale: null }]} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText('Remove a'));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
