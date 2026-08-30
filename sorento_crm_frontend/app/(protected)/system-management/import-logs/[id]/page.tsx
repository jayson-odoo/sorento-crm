'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTime } from '@/lib/helpers';
import { getImportLog } from '../services/importLogService';
import type { ImportLog } from '../types/importLog.types';

type ImportLogDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default function ImportLogDetailPage({ params }: ImportLogDetailPageProps) {
  const { id } = use(params);
  const router = useRouter();

  const { data: log, isLoading } = useQuery({
    queryKey: ['import-log', id],
    queryFn: () => getImportLog(id),
    staleTime: 1000 * 60 * 5,
    retry: 1,
  });

  if (isLoading) {
    return (
      <>
        <Container>
          <PageHeader
            title="Import Log"
            actions={
              <Button asChild variant="outline">
                <Link href="/system-management/import-logs">
                  <MoveLeft /> Back to Import Logs
                </Link>
              </Button>
            }
          />
        </Container>
        <Container>
          <div className="space-y-6">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-96 w-full" />
          </div>
        </Container>
      </>
    );
  }

  if (!log) {
    return (
      <>
        <Container>
          <PageHeader
            title="Import Log"
            actions={
              <Button asChild variant="outline">
                <Link href="/system-management/import-logs">
                  <MoveLeft /> Back to Import Logs
                </Link>
              </Button>
            }
          />
        </Container>
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Import log not found</p>
            <Button variant="outline" onClick={() => router.push('/system-management/import-logs')} className="mt-4">
              Back to Import Logs
            </Button>
          </div>
        </Container>
      </>
    );
  }

  // Parse warnings and errors
  const warnings = Array.isArray(log.warnings) ? log.warnings : [];
  const errors = Array.isArray(log.errors) ? log.errors : [];

  return (
    <>
      <Container>
        <PageHeader
          title="Import Log Details"
          actions={
            <Button asChild variant="outline">
              <Link href="/system-management/import-logs">
                <MoveLeft /> Back to Import Logs
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <div className="space-y-6">
          {/* Summary Card */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Import Summary</CardTitle>
                <Badge variant={log.failed_rows > 0 ? 'destructive' : 'secondary'}>
                  {log.entity_type} • {log.import_type}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Total Rows</p>
                  <p className="font-medium text-lg">{log.total_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Successful</p>
                  <p className="font-medium text-lg text-emerald-600">{log.successful_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Skipped</p>
                  <p className="font-medium text-lg text-yellow-600">{log.skipped_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Failed</p>
                  <p className="font-medium text-lg text-red-600">{log.failed_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Created</p>
                  <p className="font-medium">{log.created_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Updated</p>
                  <p className="font-medium">{log.updated_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Imported By</p>
                  <p className="font-medium">{log.imported_by || '-'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Imported At</p>
                  <p className="font-medium">{formatDateTime(new Date(log.imported_at))}</p>
                </div>
                {log.duration_ms && (
                  <div>
                    <p className="text-muted-foreground">Duration</p>
                    <p className="font-medium">{log.duration_ms} ms</p>
                  </div>
                )}
                {log.filename && (
                  <div>
                    <p className="text-muted-foreground">Filename</p>
                    <p className="font-medium">{log.filename}</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Errors Card */}
          {errors.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-red-600">Errors ({errors.length})</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {errors.map((error: any, index: number) => (
                    <div key={index} className="border-l-4 border-red-500 pl-4 py-2 bg-red-50 dark:bg-red-950/20 rounded">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <p className="font-medium text-sm">
                            Row {error.row !== undefined ? error.row + 1 : 'N/A'}
                            {error.product_code && (
                              <span className="text-muted-foreground ml-2">• Product: {error.product_code}</span>
                            )}
                            {error.warehouse && (
                              <span className="text-muted-foreground ml-2">• Warehouse: {error.warehouse}</span>
                            )}
                          </p>
                          <p className="text-sm text-red-700 dark:text-red-400 mt-1">{error.error || error.message || 'Unknown error'}</p>
                          {error.data && typeof error.data === 'object' && (
                            <div className="mt-2 text-xs text-muted-foreground">
                              <pre className="whitespace-pre-wrap">{JSON.stringify(error.data, null, 2)}</pre>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Warnings Card */}
          {warnings.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-yellow-600">Warnings ({warnings.length})</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {warnings.map((warning: any, index: number) => (
                    <div key={index} className="border-l-4 border-yellow-500 pl-4 py-2 bg-yellow-50 dark:bg-yellow-950/20 rounded">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <p className="font-medium text-sm">
                            Row {warning.row !== undefined ? warning.row + 1 : 'N/A'}
                            {warning.product_code && (
                              <span className="text-muted-foreground ml-2">• Product: {warning.product_code}</span>
                            )}
                            {warning.warehouse && (
                              <span className="text-muted-foreground ml-2">• Warehouse: {warning.warehouse}</span>
                            )}
                          </p>
                          <p className="text-sm text-yellow-700 dark:text-yellow-400 mt-1">{warning.reason || warning.message || 'Warning'}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Summary JSON (if available) */}
          {log.summary && typeof log.summary === 'object' && Object.keys(log.summary).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Additional Summary</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="text-xs bg-muted p-4 rounded overflow-auto">
                  {JSON.stringify(log.summary, null, 2)}
                </pre>
              </CardContent>
            </Card>
          )}
        </div>
      </Container>
    </>
  );
}
