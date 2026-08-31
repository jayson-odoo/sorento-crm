'use client';

/**
 * Tag template editor page.
 *
 * Loads the template by id from the mock service and renders the full
 * TagCanvasEditor. Save button calls updateTemplate.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { toast } from 'sonner';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { Skeleton } from '@/components/ui/skeleton';
import dynamic from 'next/dynamic';
import type { TagTemplate, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { getTemplate, updateTemplate } from '../../services/tagTemplateService';

const TagCanvasEditor = dynamic(
  () => import('../components/TagCanvasEditor').then((m) => ({ default: m.TagCanvasEditor })),
  { ssr: false, loading: () => <Skeleton className="h-[400px] w-full" /> },
);

export default function TagTemplateEditorPage() {
  const params = useParams<{ id: string }>();

  const [template, setTemplate] = useState<TagTemplate | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    getTemplate(params.id)
      .then((t) => {
        if (!cancelled) setTemplate(t);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load template');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  const handleSave = useCallback(
    async (doc: TagTemplateDoc) => {
      if (!template) return;
      try {
        const updated = await updateTemplate(template.id, doc);
        setTemplate(updated);
        toast.success('Template saved');
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Could not save template');
      }
    },
    [template],
  );

  if (isLoading) {
    return (
      <Container>
        <PageHeader title={<Skeleton className="h-6 w-48" />} crumbTitle="Loading" />
        <Skeleton className="mt-4 h-[400px] w-full" />
      </Container>
    );
  }

  if (error || !template) {
    return (
      <Container>
        <PageHeader
          title="Template not found"
          actions={
            <BackToList listPath="/dealer-kit/tag-templates" label="Back to templates" />
          }
        />
        <p className="mt-4 text-sm text-destructive">{error ?? 'Template not found'}</p>
      </Container>
    );
  }

  return (
    <div className="flex h-[calc(100dvh-var(--header-height)-20px)] flex-col">
      {/* Header: PageHeader keeps the trail and title one component and one
          scale (S5-01, S5-02) even though this shell sits outside the normal
          scrolling Toolbar rhythm - shrink-0 so the canvas below still gets
          whatever height is left, exactly as the old compact bar did.
          The 100dvh subtracts the fixed top bar's own height (the demo1
          layout's `--header-height`, 70px desktop / 60px below lg) plus the
          `<main>` wrapper's `pt-5` (20px) - both chrome above this div that a
          flat 56px never accounted for and left the canvas short. */}
      <div className="shrink-0 border-b">
        <Container>
          <PageHeader
            title={template.name}
            actions={
              <BackToList listPath="/dealer-kit/tag-templates" label="Back to templates" />
            }
          />
        </Container>
      </div>

      {/* Canvas editor fills remaining height */}
      <div className="flex-1 overflow-hidden">
        <TagCanvasEditor doc={template.doc} onChange={handleSave} />
      </div>
    </div>
  );
}
