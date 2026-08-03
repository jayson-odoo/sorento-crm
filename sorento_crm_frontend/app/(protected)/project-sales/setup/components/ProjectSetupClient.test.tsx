/**
 * ProjectSetupClient, converted from a dual-panel card stack to two standard lists.
 *
 * The master-detail relationship is real and has to survive the conversion: picking a
 * TYPE row filters the templates beside it, and picking a TEMPLATE row loads its
 * checklist below. Both are expressed as rows in a proper list with their own toolbar,
 * not as bordered blocks with floating pencil and bin icons.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectTemplate, ProjectType } from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listProjectTypes = vi.fn();
const listProjectTemplates = vi.fn();
const listTemplateTasks = vi.fn();
const listingKeys: (string | null | undefined)[] = [];

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/setup',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: async () => {}, isLoading: false };
  },
}));

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listProjectTypes: (...args: unknown[]) => listProjectTypes(...args),
    listProjectTemplates: (...args: unknown[]) => listProjectTemplates(...args),
    listTemplateTasks: (...args: unknown[]) => listTemplateTasks(...args),
    createProjectType: vi.fn(),
    updateProjectType: vi.fn(),
    deleteProjectType: vi.fn(async () => undefined),
    createProjectTemplate: vi.fn(),
    updateProjectTemplate: vi.fn(),
    deleteProjectTemplate: vi.fn(async () => undefined),
  };
});

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

import { ProjectSetupClient } from './ProjectSetupClient';

function projectType(overrides: Partial<ProjectType> = {}): ProjectType {
  return {
    id: 't1',
    name: 'Property development',
    code: 'PROP',
    derives_delivery_from_launch: true,
    sort_order: 1,
    is_active: true,
    template_count: 2,
    ...overrides,
  };
}

function template(overrides: Partial<ProjectTemplate> = {}): ProjectTemplate {
  return {
    id: 'tp1',
    type_id: 't1',
    name: 'New build',
    is_active: true,
    roles: [{ id: 'r1', name: 'Architect', sort_order: 0, is_active: true }],
    has_forked_status_graph: false,
    ...overrides,
  };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProjectSetupClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  listProjectTypes.mockResolvedValue([]);
  listProjectTemplates.mockResolvedValue([]);
  listTemplateTasks.mockResolvedValue([]);
});

describe('ProjectSetupClient', () => {
  it('gives each level its own toolbar row with an Add action', async () => {
    const typesHeader = await (async () => {
      renderClient();
      return (
        await screen.findByRole('heading', { name: 'Project types' })
      ).closest('[data-slot="card-header"]') as HTMLElement;
    })();

    expect(within(typesHeader).getByRole('button', { name: 'Add type' })).toBeInTheDocument();
    expect(within(typesHeader).getByRole('button', { name: /columns/i })).toBeInTheDocument();
    expect(within(typesHeader).getByRole('button', { name: /^export$/i })).toBeInTheDocument();

    const templatesHeader = (
      await screen.findByRole('heading', { name: 'Templates' })
    ).closest('[data-slot="card-header"]') as HTMLElement;
    expect(
      within(templatesHeader).getByRole('button', { name: 'Add template' }),
    ).toBeInTheDocument();
  });

  it('pins a listing key per list rather than falling back to the pathname', async () => {
    renderClient();

    await waitFor(() => expect(listingKeys.length).toBeGreaterThan(1));
    expect(listingKeys).toContain('projects.types.view::types');
    expect(listingKeys).toContain('projects.types.view::templates');
    expect(listingKeys).not.toContain('/project-sales/setup');
  });

  it('says what a type is when there are none, and offers the first one', async () => {
    renderClient();

    expect(await screen.findByText('No project types yet')).toBeInTheDocument();
    expect(
      screen.getByText(/A type is the kind of job: property development, hotel, fitout/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add the first type' }),
    ).toBeInTheDocument();
  });

  it('asks for a type before it can show templates', async () => {
    renderClient();

    expect(await screen.findByText('No project type selected')).toBeInTheDocument();
    expect(
      screen.getByText('Select a project type to see its templates.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add template' })).toBeDisabled();
  });

  it('renders a row per type and lands on the first one, which loads its templates', async () => {
    listProjectTypes.mockResolvedValue([
      projectType({ id: 't1', name: 'Property development' }),
      projectType({ id: 't2', name: 'Hotel', code: 'HOTEL', derives_delivery_from_launch: false }),
    ]);
    listProjectTemplates.mockResolvedValue([template()]);

    renderClient();

    expect(await screen.findByText('Property development')).toBeInTheDocument();
    expect(screen.getByText('Hotel')).toBeInTheDocument();
    expect(screen.getByText('Delivery from launch')).toBeInTheDocument();
    expect(screen.getByText('Stated per project')).toBeInTheDocument();
    expect(screen.getAllByText('2 templates')).toHaveLength(2);

    // Landing on the first type is what makes the templates list non-empty.
    await waitFor(() => expect(listProjectTemplates).toHaveBeenCalledWith('t1'));
    expect(await screen.findByText('New build')).toBeInTheDocument();
    expect(screen.getByText('1 roles: Architect')).toBeInTheDocument();
  });

  it('re-filters the templates when another type row is clicked', async () => {
    listProjectTypes.mockResolvedValue([
      projectType({ id: 't1', name: 'Property development' }),
      projectType({ id: 't2', name: 'Hotel', code: 'HOTEL' }),
    ]);

    renderClient();
    await waitFor(() => expect(listProjectTemplates).toHaveBeenCalledWith('t1'));

    fireEvent.click(await screen.findByText('Hotel'));

    await waitFor(() => expect(listProjectTemplates).toHaveBeenCalledWith('t2'));
  });

  it('loads the checklist for the template row that was clicked', async () => {
    listProjectTypes.mockResolvedValue([projectType()]);
    listProjectTemplates.mockResolvedValue([template({ id: 'tp1', name: 'New build' })]);

    renderClient();

    // Nothing picked yet, so the checklist panel says what to do.
    expect(
      await screen.findByText(/Select a template above to edit the checklist/i),
    ).toBeInTheDocument();

    fireEvent.click(await screen.findByText('New build'));

    await waitFor(() => expect(listTemplateTasks).toHaveBeenCalledWith('tp1'));
  });

  it('confirms before deleting a type, and says it cannot be undone', async () => {
    listProjectTypes.mockResolvedValue([projectType()]);

    renderClient();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete Property development' }),
    );

    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument();
  });
});
