import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { AgentModelCard } from './AgentModelCard';

/**
 * AGENTIC-REASONING-VIS round 2 (owner, 31 Oct: "how do I set reasoning effort"), red first.
 *
 * The "Runs on" card gets a clearable `Reasoning effort` select beside Provider and Model. Its value comes from
 * the key list's `reasoning_effort`; Save sends `reasoning_effort` with the provider and model ("" clears it).
 */

const mutateAsync = vi.fn();
const usePromptKeys = vi.fn();

vi.mock('../../hooks/useAIAssistantPrompts', () => ({
  usePromptKeys: () => usePromptKeys(),
  useSetAgentModel: () => ({ mutateAsync, isPending: false }),
}));
vi.mock('@/hooks/useProviderModels', () => ({ useProviderModels: () => ({ data: undefined }) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    clearable?: boolean;
    disabled?: boolean;
    'aria-label'?: string;
  }) => (
    <select
      aria-label={props['aria-label']}
      data-clearable={props.clearable ? 'true' : 'false'}
      value={props.value}
      disabled={props.disabled}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">Default</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

function keys(effort: string | null) {
  usePromptKeys.mockReturnValue({
    data: [{ name: 'chatbot_agent', provider: null, model: null, reasoning_effort: effort }],
  });
}

beforeEach(() => {
  mutateAsync.mockReset().mockResolvedValue({});
});

afterEach(() => cleanup());

describe('the Runs on card sets the reasoning effort', () => {
  it('shows the saved effort in a clearable select', () => {
    keys('low');
    render(<AgentModelCard name="chatbot_agent" canEdit />);
    const select = screen.getByRole('combobox', { name: 'Reasoning effort' }) as HTMLSelectElement;
    expect(select.value).toBe('low');
    expect(select).toHaveAttribute('data-clearable', 'true');
    for (const label of ['None', 'Minimal', 'Low', 'Medium', 'High']) {
      expect(screen.getByRole('option', { name: label })).toBeInTheDocument();
    }
  });

  it('saves a new effort with the model', async () => {
    keys(null);
    render(<AgentModelCard name="chatbot_agent" canEdit />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Reasoning effort' }), { target: { value: 'medium' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    expect(mutateAsync).toHaveBeenCalledWith({ provider: null, model: null, reasoning_effort: 'medium' });
  });

  it('clearing the effort sends an empty value', async () => {
    keys('low');
    render(<AgentModelCard name="chatbot_agent" canEdit />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Reasoning effort' }), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    expect(mutateAsync).toHaveBeenCalledWith({ provider: null, model: null, reasoning_effort: '' });
  });

  it('is read-only without the edit permission', () => {
    keys('low');
    render(<AgentModelCard name="chatbot_agent" canEdit={false} />);
    expect(screen.getByRole('combobox', { name: 'Reasoning effort' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: /save/i })).toBeNull();
  });
});
