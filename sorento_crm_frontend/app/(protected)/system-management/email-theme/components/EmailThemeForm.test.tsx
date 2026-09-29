/**
 * S7 - the Email Theme page: renders every section/field, the selects are
 * `SearchableSelect`, typing a colour updates both the swatch and the hex
 * box, Save calls the mutation with blank fields turned to null, and the
 * preview fires (debounced) after a form edit (AC-EM020/021/030, AC-EM091).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  usePathname: () => '/system-management/email-theme',
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title, actions }: { title: React.ReactNode; actions?: React.ReactNode }) => (
    <header>
      <h1>{title}</h1>
      <div data-testid="header-actions">{actions}</div>
    </header>
  ),
}));

const THEME_RESPONSE = {
  theme: {
    logo_url: null,
    logo_alignment: null,
    logo_height: null,
    header_style: null,
    primary_color: '#2563EB',
    accent_color: null,
    page_background: null,
    button_color: null,
    button_text_color: null,
    button_radius: null,
    button_width: null,
    card_radius: null,
    font: null,
    company_name: 'Sorento',
    address: null,
    help_email: null,
    help_url: null,
    footer_note: null,
    social_links: null,
  },
  defaults: {
    logo_url: 'https://cdn.example.com/logo.png',
    logo_alignment: 'center',
    logo_height: 40,
    header_style: 'brand',
    primary_color: '#2563EB',
    accent_color: '#2563EB',
    page_background: '#F3F4F6',
    button_color: '#2563EB',
    button_text_color: '#FFFFFF',
    button_radius: 8,
    button_width: 'auto',
    card_radius: 12,
    font: 'system',
    company_name: 'Sorento',
    address: '123 Example Street',
    help_email: 'help@example.com',
    help_url: 'https://example.com/help',
    footer_note: 'You received this because you have an account with us.',
    social_links: [],
  },
  fonts: [
    { value: 'system', label: 'System default' },
    { value: 'arial', label: 'Arial' },
  ],
};

const saveMut = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const previewMut = vi.hoisted(() => ({ mutate: vi.fn(), isPending: false, data: undefined as unknown }));
const themeQueryState = vi.hoisted(() => ({
  data: undefined as typeof THEME_RESPONSE | undefined,
  isLoading: false,
}));

vi.mock('../hooks/useEmailTheme', () => ({
  useEmailThemeQuery: () => themeQueryState,
  useSaveEmailThemeMutation: () => saveMut,
  useEmailThemePreview: () => previewMut,
}));

import EmailThemeForm from './EmailThemeForm';

beforeEach(() => {
  vi.useFakeTimers();
  saveMut.mutateAsync.mockReset();
  saveMut.mutateAsync.mockResolvedValue(THEME_RESPONSE);
  previewMut.mutate.mockReset();
  themeQueryState.data = THEME_RESPONSE;
  themeQueryState.isLoading = false;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('EmailThemeForm', () => {
  it('renders every section and field', () => {
    render(<EmailThemeForm />);

    expect(screen.getByRole('heading', { name: 'Email Theme' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Brand' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Button' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Text' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Footer' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Card' })).toBeInTheDocument();

    expect(screen.getByLabelText('Logo URL')).toBeInTheDocument();
    expect(screen.getByLabelText('Logo height (px)')).toBeInTheDocument();
    expect(screen.getByLabelText('Company name')).toBeInTheDocument();
    expect(screen.getByLabelText('Help email')).toBeInTheDocument();
    expect(screen.getByLabelText('Help URL')).toBeInTheDocument();
    expect(screen.getByLabelText('Address')).toBeInTheDocument();
    expect(screen.getByLabelText('Why you received this')).toBeInTheDocument();
    expect(screen.getByText('Social links')).toBeInTheDocument();
    // "Corner radius (px)" is shared by Button and Card - both must render.
    expect(screen.getAllByLabelText('Corner radius (px)')).toHaveLength(2);

    // One primary CTA in the header, no subtitle under the title.
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });

  it('every optional select in the form is the SearchableSelect combobox trigger', () => {
    render(<EmailThemeForm />);

    // Logo alignment, header style, button width, font - four optional
    // selects, every one a `role="combobox"` trigger (SearchableSelect).
    const combos = screen.getAllByRole('combobox');
    expect(combos.length).toBeGreaterThanOrEqual(4);
  });

  it('typing a colour updates both the swatch and the hex text box', () => {
    render(<EmailThemeForm />);

    const hexInput = screen.getByLabelText('Primary colour') as HTMLInputElement;
    const swatch = screen.getByLabelText('Primary colour swatch') as HTMLInputElement;

    expect(hexInput.value).toBe('#2563EB');

    fireEvent.change(hexInput, { target: { value: '#ff0000' } });

    expect(hexInput.value).toBe('#ff0000');
    expect(swatch.value).toBe('#ff0000');
  });

  it('Save calls the mutation with blank fields turned to null', async () => {
    // Real timers for this one: `waitFor` polls on a real `setTimeout`, which
    // a faked clock never advances on its own.
    vi.useRealTimers();
    render(<EmailThemeForm />);

    const companyNameInput = screen.getByLabelText('Company name') as HTMLInputElement;
    fireEvent.change(companyNameInput, { target: { value: '' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(saveMut.mutateAsync).toHaveBeenCalledTimes(1));
    const payload = saveMut.mutateAsync.mock.calls[0][0];
    expect(payload.company_name).toBeNull();
    // A field left untouched from the stored theme still round-trips.
    expect(payload.primary_color).toBe('#2563EB');
  });

  it('requests a preview render (debounced) after a form edit', () => {
    render(<EmailThemeForm />);

    previewMut.mutate.mockClear();
    const companyNameInput = screen.getByLabelText('Company name');
    fireEvent.change(companyNameInput, { target: { value: 'New Co' } });

    expect(previewMut.mutate).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(400);
    });

    // The mutation variable is { theme, code } since the Sample mail select (AC-EM032).
    expect(previewMut.mutate).toHaveBeenCalledWith({
      theme: expect.objectContaining({ company_name: 'New Co' }),
      code: 'auth_password_reset',
    });
  });

  describe('Sample mail select (AC-EM032)', () => {
    const LABELS = [
      'Password reset',
      'User invitation',
      'Onboarding intake link',
      'Purchase request approval link',
    ];

    it('renders with Password reset selected and offers exactly the four credential mails', () => {
      render(<EmailThemeForm />);

      const trigger = screen.getByLabelText('Sample mail');
      expect(trigger).toHaveTextContent('Password reset');

      fireEvent.click(trigger);
      const options = screen.getAllByRole('option');
      expect(options.map((o) => o.textContent)).toEqual(LABELS);
    });

    it('the initial preview request carries the default code', () => {
      render(<EmailThemeForm />);

      act(() => {
        vi.advanceTimersByTime(400);
      });

      expect(previewMut.mutate).toHaveBeenCalledWith({
        theme: expect.objectContaining({ primary_color: '#2563EB' }),
        code: 'auth_password_reset',
      });
    });

    it('choosing User invitation previews that mail with the current theme payload', () => {
      render(<EmailThemeForm />);
      act(() => {
        vi.advanceTimersByTime(400);
      });
      previewMut.mutate.mockClear();

      fireEvent.click(screen.getByLabelText('Sample mail'));
      fireEvent.click(screen.getByRole('option', { name: 'User invitation' }));
      act(() => {
        vi.advanceTimersByTime(400);
      });

      expect(previewMut.mutate).toHaveBeenCalledWith({
        theme: expect.objectContaining({ primary_color: '#2563EB', company_name: 'Sorento' }),
        code: 'user_invitation',
      });
    });

    it('Save never sends the sample code', async () => {
      vi.useRealTimers();
      render(<EmailThemeForm />);

      fireEvent.click(screen.getByLabelText('Sample mail'));
      fireEvent.click(screen.getByRole('option', { name: 'User invitation' }));
      fireEvent.click(screen.getByRole('button', { name: 'Save' }));

      await waitFor(() => expect(saveMut.mutateAsync).toHaveBeenCalledTimes(1));
      expect(saveMut.mutateAsync.mock.calls[0][0]).not.toHaveProperty('code');
    });
  });
});
