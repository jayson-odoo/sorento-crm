'use client';

/**
 * Tag template editor page.
 *
 * Loads the template by id from the mock service and renders the full
 * TagCanvasEditor. Save button calls updateTemplate.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
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
  const router = useRouter();

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
            <Button variant="outline" onClick={() => router.push('/dealer-kit/tag-templates')}>
              <ArrowLeft className="mr-1.5 size-4" />
              Back to templates
            </Button>
          }
        />
        <p className="mt-4 text-sm text-destructive">{error ?? 'Template not found'}</p>
      </Container>
    );
  }

  return (
    <div className="flex h-[calc(100dvh-56px)] flex-col">
      {/* Header */}
      <div className="shrink-0 border-b px-4 py-2">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold">{template.name}</h1>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/dealer-kit">Dealer Kit</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/dealer-kit/tag-templates">
                    Tag Templates
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>{template.name}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push('/dealer-kit/tag-templates')}
          >
            <ArrowLeft className="mr-1.5 size-3.5" />
            Back
          </Button>
        </div>
      </div>

      {/* Canvas editor fills remaining height */}
      <div className="flex-1 overflow-hidden">
        <TagCanvasEditor doc={template.doc} onChange={handleSave} />
      </div>
    </div>
  );
}
