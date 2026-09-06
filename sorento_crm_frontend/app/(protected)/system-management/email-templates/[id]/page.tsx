'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { Badge } from '@/components/ui/badge';
import {
  useEmailTemplate,
  usePreviewEmailTemplate,
} from '../hooks/useEmailTemplates';
import EmailTemplateForm from '../components/EmailTemplateForm';

export default function EmailTemplateDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id ?? null;
  const { data: template, isLoading, refetch } = useEmailTemplate(id);
  const previewMut = usePreviewEmailTemplate(id);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (id) {
      previewMut.mutate(undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, template?.updated_at]);

  const previewSubject = previewMut.data?.subject ?? '';
  const previewHtml = useMemo(() => previewMut.data?.body_html ?? '', [previewMut.data]);

  return (
    <>
      <Container>
        <PageHeader
          title={template?.name ?? 'Email Template'}
          actions={
            <>
              <Button variant="outline" size="sm" onClick={() => router.push('/system-management/email-templates')}>
                <ArrowLeft className="mr-1 size-4" /> Back
              </Button>
              <Button size="sm" onClick={() => setEditing(true)} disabled={!template}>
                <Pencil className="mr-1 size-4" /> Edit
              </Button>
            </>
          }
        />
      </Container>

      <Container>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Overview</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {isLoading || !template ? (
                <SectionSkeleton rows={3} />
              ) : (
                <>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Code</span>
                    <span className="font-mono">{template.code}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Active</span>
                    <Badge variant={template.is_active ? 'success' : 'secondary'}>
                      {template.is_active ? 'Yes' : 'No'}
                    </Badge>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Subject (raw)</span>
                    <span className="font-mono text-right">{template.subject}</span>
                  </div>
                  {template.description && (
                    <div>
                      <span className="text-muted-foreground">Description</span>
                      <p className="mt-1">{template.description}</p>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Preview (sample data)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {previewMut.isPending ? (
                <p className="text-muted-foreground text-sm">Rendering…</p>
              ) : previewMut.data ? (
                <>
                  <div>
                    <p className="text-xs text-muted-foreground">Subject</p>
                    <p className="font-medium">{previewSubject}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Body HTML</p>
                    <iframe
                      title="email-preview"
                      sandbox=""
                      className="w-full min-h-[300px] border rounded bg-white"
                      srcDoc={previewHtml}
                    />
                  </div>
                </>
              ) : (
                <p className="text-muted-foreground text-sm">No preview yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </Container>

      <EmailTemplateForm
        open={editing}
        onOpenChange={setEditing}
        template={template ?? null}
        onSaved={() => void refetch()}
      />
    </>
  );
}
