import * as React from 'react';
import Link from 'next/link';
import type { ProjectRegistrationDuplicate } from '@/types/projectRegistration';

/**
 * The existing projects a registration may repeat, each a link to that project.
 * Nothing is shown when there are none; the caller decides what an empty state reads.
 */
export function ProjectRegistrationDuplicates({
  items,
  className,
}: {
  items: ProjectRegistrationDuplicate[];
  className?: string;
}) {
  const title = items.map((d) => `${d.project_code} ${d.title}`).join(', ');
  return (
    <span className={`min-w-0 truncate ${className ?? ''}`} title={title}>
      {items.map((d, index) => (
        <React.Fragment key={d.project_id}>
          {index > 0 && ', '}
          <Link
            href={`/project-sales/${d.project_id}`}
            className="text-primary hover:underline"
            onClick={(event) => event.stopPropagation()}
          >
            {d.project_code} {d.title}
          </Link>
        </React.Fragment>
      ))}
    </span>
  );
}
