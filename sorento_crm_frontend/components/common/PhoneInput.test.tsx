import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { PhoneInput, normalisePhone } from './PhoneInput';

describe('normalisePhone (Malaysia default)', () => {
  it.each([
    ['0166753328'],
    ['60166753328'],
    ['+60 16-675 3328'],
    ['+60166753328'],
    ['0060166753328'],
    ['016-675 3328'],
  ])('%s normalises to +60166753328, shown as 016-675 3328', (raw) => {
    expect(normalisePhone(raw, 'MY')).toEqual({
      e164: '+60166753328',
      display: '016-675 3328',
      country: 'MY',
      valid: true,
    });
  });

  it('an incomplete number is not valid and keeps its as-typed format', () => {
    const out = normalisePhone('016675', 'MY');
    expect(out.valid).toBe(false);
    expect(out.display).toBe('016-675');
  });

  it('a pasted number from another country switches the country', () => {
    expect(normalisePhone('+65 9123 4567', 'MY')).toMatchObject({
      e164: '+6591234567',
      country: 'SG',
      valid: true,
    });
  });

  it('empty input is empty, not an error', () => {
    expect(normalisePhone('   ', 'MY')).toEqual({ e164: '', display: '', country: 'MY', valid: false });
  });
});

function Harness({ onChange, showError }: { onChange?: (v: string, meta: { valid: boolean }) => void; showError?: boolean }) {
  const [value, setValue] = React.useState('');
  return (
    <>
      <label htmlFor="p">Phone number</label>
      <PhoneInput
        id="p"
        value={value}
        showError={showError}
        onChange={(v, meta) => {
          setValue(v);
          onChange?.(v, meta);
        }}
      />
      <output data-testid="value">{value}</output>
    </>
  );
}

const field = () => screen.getByLabelText('Phone number') as HTMLInputElement;

describe('PhoneInput', () => {
  it('defaults to Malaysia: flag trigger names Malaysia (+60) and the dial code shows', () => {
    render(<Harness />);
    expect(screen.getByRole('button', { name: 'Country: Malaysia (+60)' })).toBeInTheDocument();
    expect(screen.getByText('+60')).toBeInTheDocument();
    expect(field()).toHaveAttribute('type', 'tel');
  });

  it.each([['0166753328'], ['60166753328'], ['+60 16-675 3328']])(
    'pasting %s shows 016-675 3328 and emits +60166753328 as valid',
    (raw) => {
      const onChange = vi.fn();
      render(<Harness onChange={onChange} />);
      fireEvent.change(field(), { target: { value: raw } });
      expect(field().value).toBe('016-675 3328');
      expect(screen.getByTestId('value').textContent).toBe('+60166753328');
      expect(onChange).toHaveBeenLastCalledWith('+60166753328', { valid: true, country: 'MY' });
    },
  );

  it('formats as typed, digit by digit', () => {
    render(<Harness />);
    let typed = '';
    for (const d of '0166753328') {
      typed = field().value.replace(/\D/g, '') + d;
      fireEvent.change(field(), { target: { value: typed } });
    }
    expect(field().value).toBe('016-675 3328');
  });

  it('an incomplete number shows no error while typing, then the error state on blur', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.change(field(), { target: { value: '016675' } });
    expect(onChange).toHaveBeenLastCalledWith(expect.any(String), { valid: false, country: 'MY' });
    expect(screen.queryByRole('alert')).toBeNull();
    expect(field()).not.toHaveAttribute('aria-invalid');

    fireEvent.blur(field());
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a complete phone number.');
    expect(field()).toHaveAttribute('aria-invalid', 'true');
    expect(field()).toHaveAttribute('aria-describedby', 'p-error');
    expect(document.querySelector('[data-slot="phone-input"]')).toHaveAttribute('data-invalid', 'true');
  });

  it('completing the number clears the error state', () => {
    render(<Harness />);
    fireEvent.change(field(), { target: { value: '016675' } });
    fireEvent.blur(field());
    expect(screen.getByRole('alert')).toBeInTheDocument();
    fireEvent.change(field(), { target: { value: '0166753328' } });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('showError forces the error state for an incomplete number without a blur', () => {
    render(<Harness showError />);
    fireEvent.change(field(), { target: { value: '0123' } });
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('disabled disables both the country picker and the number', () => {
    render(<PhoneInput value="" onChange={vi.fn()} disabled aria-label="Phone" />);
    expect(screen.getByLabelText('Phone')).toBeDisabled();
    expect(screen.getByRole('button', { name: /Country:/ })).toBeDisabled();
  });

  it('seeds the national format from an E.164 value', () => {
    render(<PhoneInput value="+60166753328" onChange={vi.fn()} aria-label="Phone" />);
    expect((screen.getByLabelText('Phone') as HTMLInputElement).value).toBe('016-675 3328');
  });

  it('picking another country re-reads the digits against it', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.change(field(), { target: { value: '91234567' } });
    fireEvent.click(screen.getByRole('button', { name: 'Country: Malaysia (+60)' }));
    fireEvent.change(await screen.findByPlaceholderText('Search...'), { target: { value: 'Singapore' } });
    fireEvent.click(await screen.findByRole('option', { name: /Singapore/ }));
    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith('+6591234567', { valid: true, country: 'SG' }),
    );
    expect(screen.getByRole('button', { name: 'Country: Singapore (+65)' })).toBeInTheDocument();
  });
});
