/** SEARCH-CHIPS slice 1 (UAC F1-F4, F6, F7, F9): `ListSearchInput` chips mode, switched on by passing
 * `onChipsChange` (props `chips?: string[]`, `onChipsChange?: (next: string[]) => void`); the text half
 * (`value` / `onChange`) is unchanged. Red first: the props do not exist yet.
 * F6's "+N" collapse is layout (widths) that jsdom cannot measure; here only "every chip is
 * rendered and reachable" is asserted, the collapse itself is left to the browser pass. */
import React, { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ListSearchInput } from './ListSearchInput';

type ChipProps = {
  chips?: string[];
  onChipsChange?: (next: string[]) => void;
};

// Cast so this file type-checks before the props exist; the behaviour is what is under test.
const ChipsBox = ListSearchInput as unknown as React.ComponentType<
  React.ComponentProps<typeof ListSearchInput> & ChipProps
>;

function Harness({
  initialChips = [],
  initialValue = '',
  onSubmit,
}: {
  initialChips?: string[];
  initialValue?: string;
  onSubmit?: () => void;
}) {
  const [chips, setChips] = useState<string[]>(initialChips);
  const [value, setValue] = useState(initialValue);
  return (
    <>
      <ChipsBox
        value={value}
        onChange={(next) => {
          spies.onChange(next);
          setValue(next);
        }}
        chips={chips}
        onChipsChange={(next) => {
          spies.onChipsChange(next);
          setChips(next);
        }}
        onSubmit={onSubmit}
        placeholder="Search SO, customer, product or agent..."
      />
      <output data-testid="chips">{JSON.stringify(chips)}</output>
      <output data-testid="text">{value}</output>
    </>
  );
}

const spies = { onChange: vi.fn(), onChipsChange: vi.fn() };

function input() {
  return screen.getByRole('textbox', { name: 'Search SO, customer, product or agent...' });
}

function chipsNow(): string[] {
  return JSON.parse(screen.getByTestId('chips').textContent || '[]');
}

function setup(props: Parameters<typeof Harness>[0] = {}) {
  spies.onChange.mockReset();
  spies.onChipsChange.mockReset();
  const user = userEvent.setup();
  render(<Harness {...props} />);
  return user;
}

describe('ListSearchInput without chips (F1)', () => {
  it('behaves as today: typing calls onChange, Enter calls onSubmit, a comma is plain text', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    function Plain() {
      const [v, setV] = useState('');
      return (
        <ListSearchInput
          value={v}
          onChange={(n) => {
            onChange(n);
            setV(n);
          }}
          onSubmit={onSubmit}
          placeholder="Search..."
        />
      );
    }
    render(<Plain />);
    const box = screen.getByRole('textbox', { name: 'Search...' });
    await user.type(box, 'SO1,SO2{Enter}');
    expect(box).toHaveValue('SO1,SO2');
    expect(onChange).toHaveBeenLastCalledWith('SO1,SO2');
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: /^Remove / })).toBeNull();
  });
});

describe('ListSearchInput chips mode', () => {
  it('F2: Enter turns the typed text into a chip and empties the text', async () => {
    const user = setup();
    await user.type(input(), 'SO371334{Enter}');
    expect(spies.onChipsChange).toHaveBeenLastCalledWith(['SO371334']);
    expect(chipsNow()).toEqual(['SO371334']);
    expect(input()).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Remove SO371334' })).toBeInTheDocument();
  });

  it('F2: a comma commits the chip too, and the comma is not kept', async () => {
    const user = setup();
    await user.type(input(), 'SO1,Acme Trading,');
    expect(chipsNow()).toEqual(['SO1', 'Acme Trading']);
    expect(input()).toHaveValue('');
  });

  it('F2: blank text makes no chip', async () => {
    const user = setup({ initialChips: ['SO1'] });
    await user.type(input(), '   {Enter}');
    expect(chipsNow()).toEqual(['SO1']);
    expect(screen.getAllByRole('button', { name: /^Remove / })).toHaveLength(1);
  });

  it('F2: a case-insensitive duplicate is not added', async () => {
    const user = setup({ initialChips: ['SO1'] });
    await user.type(input(), 'so1{Enter}');
    expect(chipsNow()).toEqual(['SO1']);
    expect(screen.getAllByRole('button', { name: /^Remove / })).toHaveLength(1);
  });

  it('F3: a paste with commas and new lines becomes one chip per non-blank piece', async () => {
    const user = setup();
    await user.click(input());
    await user.paste('SO1\nSO2, Acme Trading\n\n,');
    expect(chipsNow()).toEqual(['SO1', 'SO2', 'Acme Trading']);
    expect(input()).toHaveValue('');
  });

  it('F3: a space-separated paste splits only when every piece has a digit', async () => {
    const user = setup();
    await user.click(input());
    await user.paste('SO371334 SO371402');
    expect(chipsNow()).toEqual(['SO371334', 'SO371402']);
  });

  it('F3: a space-separated paste without digits stays one chip', async () => {
    const user = setup();
    await user.click(input());
    await user.paste('Acme Trading');
    expect(chipsNow()).toEqual(['Acme Trading']);
  });

  it('F4: each chip has an x labelled "Remove <value>" that removes it', async () => {
    const user = setup({ initialChips: ['SO1', 'SO2', 'Acme, Trading'] });
    await user.click(screen.getByRole('button', { name: 'Remove SO2' }));
    expect(spies.onChipsChange).toHaveBeenLastCalledWith(['SO1', 'Acme, Trading']);
    expect(screen.queryByRole('button', { name: 'Remove SO2' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Remove Acme, Trading' })).toBeInTheDocument();
  });

  it('F4: Backspace in empty text removes the last chip', async () => {
    const user = setup({ initialChips: ['SO1', 'SO2'] });
    await user.click(input());
    await user.keyboard('{Backspace}');
    expect(chipsNow()).toEqual(['SO1']);
  });

  it('F4: Backspace while there is text edits the text, not the chips', async () => {
    const user = setup({ initialChips: ['SO1', 'SO2'], initialValue: 'Ac' });
    await user.click(input());
    await user.keyboard('{End}{Backspace}');
    expect(chipsNow()).toEqual(['SO1', 'SO2']);
    expect(input()).toHaveValue('A');
  });

  it('F4: the box clear x removes every chip and the text', async () => {
    const user = setup({ initialChips: ['SO1', 'SO2'], initialValue: 'Acme' });
    await user.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(chipsNow()).toEqual([]);
    expect(input()).toHaveValue('');
  });

  it('F4: the clear x is offered when there are chips but no text', () => {
    setup({ initialChips: ['SO1'] });
    expect(screen.getByRole('button', { name: 'Clear search' })).toBeInTheDocument();
  });

  it('F6: every chip is rendered and reachable once the box has focus (layout collapse not tested in jsdom)', async () => {
    const many = ['SO1', 'SO2', 'SO3', 'SO4', 'SO5', 'SO6', 'SO7', 'SO8'];
    const user = setup({ initialChips: many });
    await user.click(input());
    for (const chip of many) {
      expect(screen.getByRole('button', { name: `Remove ${chip}` })).toBeInTheDocument();
    }
  });

  it('F7: Tab reaches the box', async () => {
    const user = setup({ initialChips: ['SO1'] });
    await user.tab();
    // Either the box itself or, first, a chip's own remove button: both are keyboard reachable.
    let guard = 0;
    while (document.activeElement !== input() && guard++ < 5) await user.tab();
    expect(input()).toHaveFocus();
  });

  it('F9: over 200 values keeps the first 200 and the box says so', async () => {
    const user = setup();
    await user.click(input());
    await user.paste(Array.from({ length: 201 }, (_, i) => `V${i}`).join('\n'));
    const kept = chipsNow();
    expect(kept).toHaveLength(200);
    expect(kept[0]).toBe('V0');
    expect(kept[199]).toBe('V199');
    expect(screen.getByText(/\b200\b/)).toBeInTheDocument();
  });

  it('F9: no notice when under the cap', async () => {
    const user = setup();
    await user.click(input());
    await user.paste('SO1\nSO2');
    expect(screen.queryByText(/\b200\b/)).toBeNull();
  });
});
