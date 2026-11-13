'use client';

import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { Button } from '@/components/ui/button';
import type { ListPagerPage } from '@/hooks/useListPager';
import { useProject } from '../../_shared/hooks/useProjects';
import { useReviewOriginHref } from '../../_shared/hooks/useReviewOrigin';
import { projectCodeLabel } from '../../_shared/lib/projectCode';
import { withReviewOrigin } from '../../_shared/lib/reviewOrigin';
import { getProjectSampleRequests } from '../services/sampleRequestService';

const LIST_PATH = '/project-sales/sample-requests';
const PROJECTS_PATH = '/project-sales/pipeline';

/** The project whose Samples Request tab the person came from, or null (SAMPLE-REQUEST-V2). */
export function projectFromOrigin(origin: string | null | undefined): string | null {
  const match = origin?.match(/^\/project-sales\/([0-9a-fA-F-]{36})\?tab=sample-requests$/);
  return match ? match[1] : null;
}

/**
 * Prev/next over the project's own requests when the person came from its tab (owner 11 Nov
 * 19:40: "prev/next follows the list it came from"). Same query key as the tab, so the rows are
 * the ones the person just saw; every step keeps the origin, so Back still returns to the tab.
 */
export function projectPagerQuery(projectId: string, origin: string) {
  return {
    listQueryKey: () => ['sample-requests', 'project', projectId],
    fetchPage: (): Promise<ListPagerPage> => getProjectSampleRequests(projectId),
    hrefFor: (id: string) => withReviewOrigin(`${LIST_PATH}/${id}`, origin),
  };
}

/**
 * The sample request pages' header. Back (or Cancel) and the breadcrumb follow where the person
 * came from: a project's Samples Request tab when they started there (`?from=`, guarded by
 * `isSafeReviewOrigin`), else the Sample Requests list as before (owner 11 Nov 16:30 and 19:40).
 */
export function SampleRequestPageHeader({
  title,
  mode,
  fallbackHref,
}: {
  title: string;
  /** `back` on the detail page; `cancel` on new / edit. */
  mode: 'back' | 'cancel';
  /** Where Cancel goes without an origin (the list, or the request being edited). */
  fallbackHref?: string;
}) {
  const origin = useReviewOriginHref();
  const projectId = projectFromOrigin(origin);
  const project = useProject(projectId ?? undefined);
  const crumbs = projectId
    ? [
        { title: 'Projects', path: PROJECTS_PATH },
        {
          title: project.data ? projectCodeLabel(project.data) : 'Project',
          path: origin as string,
        },
        { title },
      ]
    : undefined;

  let action;
  if (mode === 'cancel') {
    action = (
      <Button variant="outline" asChild>
        <Link href={origin ?? fallbackHref ?? LIST_PATH}>Cancel</Link>
      </Button>
    );
  } else if (origin) {
    action = (
      <Button variant="outline" asChild>
        <Link href={origin}>
          <MoveLeft /> {projectId ? 'Back to project' : 'Back'}
        </Link>
      </Button>
    );
  } else {
    action = (
      <BackToList
        hideForLimited="sample_request"
        listPath={LIST_PATH}
        label="Back to sample requests"
      />
    );
  }

  return <PageHeader title={title} crumbs={crumbs} actions={action} />;
}
