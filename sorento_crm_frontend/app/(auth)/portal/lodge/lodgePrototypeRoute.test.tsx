/**
 * `/portal/lodge` is the prototype, and its failure mode is that it looks real.
 *
 * The mock route accepts photos, shows a warranty verdict and a complaint number, and files
 * nothing. Somebody holding a portal token who lands here does the whole journey and comes
 * away believing they have reported a fault. Nothing on the screen contradicts them.
 *
 * So the rule is: an identity in the browser means there is a real journey to run, and this
 * route hands over to it. The prototype stays reachable for reviewing states - with no
 * identity, or explicitly with `?mock=1` - and says what it is when it renders.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const replace = vi.fn();
let search = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => search,
}));

const readPortalToken = vi.fn();
const readPortalSlug = vi.fn();

vi.mock('../lib/portal-client', async () => {
  const actual = await vi.importActual<typeof import('../lib/portal-client')>(
    '../lib/portal-client',
  );
  return { ...actual, readPortalToken: () => readPortalToken() };
});

vi.mock('../lib/portal-paths', async () => {
  const actual = await vi.importActual<typeof import('../lib/portal-paths')>(
    '../lib/portal-paths',
  );
  return { ...actual, readPortalSlug: () => readPortalSlug() };
});

import PortalLodgePage from './page';

beforeEach(() => {
  vi.clearAllMocks();
  search = new URLSearchParams();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('/portal/lodge', () => {
  it('hands a contact to their real journey instead of the mock', async () => {
    readPortalToken.mockReturnValue('tok_live');
    readPortalSlug.mockReturnValue('S1');

    render(<PortalLodgePage />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/portal/c/S1/lodge'));
  });

  it('renders the prototype when there is no identity to file against', async () => {
    readPortalToken.mockReturnValue(null);
    readPortalSlug.mockReturnValue(null);

    render(<PortalLodgePage />);

    await waitFor(() => expect(screen.getByText(/Preview only/i)).toBeInTheDocument());
    expect(replace).not.toHaveBeenCalled();
  });

  it('says plainly that nothing is saved, because the screen otherwise looks real', async () => {
    readPortalToken.mockReturnValue(null);
    readPortalSlug.mockReturnValue(null);

    render(<PortalLodgePage />);

    await waitFor(() =>
      expect(screen.getByText(/nothing submitted here is saved/i)).toBeInTheDocument(),
    );
  });

  it('still lets a reviewer force the mock while holding a token', async () => {
    // Reviewing the mocked extraction outcomes must not require signing out of the portal.
    readPortalToken.mockReturnValue('tok_live');
    readPortalSlug.mockReturnValue('S1');
    search = new URLSearchParams('mock=1');

    render(<PortalLodgePage />);

    await waitFor(() => expect(screen.getByText(/Preview only/i)).toBeInTheDocument());
    expect(replace).not.toHaveBeenCalled();
  });

  it('does not redirect a token with no slug, which cannot address a journey', async () => {
    readPortalToken.mockReturnValue('tok_live');
    readPortalSlug.mockReturnValue(null);

    render(<PortalLodgePage />);

    await waitFor(() => expect(screen.getByText(/Preview only/i)).toBeInTheDocument());
    expect(replace).not.toHaveBeenCalled();
  });
});
