'use client';

/**
 * What we asked this supplier to pack, at `/c/{companyCode}/supplier-request/{token}`.
 *
 * No login, no CRM chrome, no navigation. The reader is a factory in Chaozhou
 * opening a link out of an email, so every label is written twice - Chinese
 * first, because that is the language the person acting on it reads.
 *
 * READ-ONLY, and narrow on purpose: the item, the description, how many to load,
 * and their own stock figures as their last list stated them. No price, no cost,
 * no other supplier's rows, nothing to click through to. A leaked URL exposes one
 * request and stops working after thirty days.
 *
 * The company segment is cosmetic here, unlike the catalogue's: the token is
 * globally unique and is the whole credential. It is in the address so every
 * public page this system hands out has one shape.
 *
 * A plain table rather than `DataGrid`: this is a document, not a listing. There
 * is nothing to search, sort, page, resize or remember per user, and the grid's
 * column-preference machinery reads an endpoint that answers 401 to a stranger.
 */

import { use, useEffect, useState } from 'react';
import { Download, LoaderCircle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  SupplierRequestUnavailableError,
  readSupplierRequest,
  readSupplierRequestDocument,
  type SupplierRequest,
} from '../../../lib/publicSupplierRequestService';

type Status =
  | { state: 'loading' }
  | { state: 'ready'; request: SupplierRequest }
  | { state: 'missing' }
  | { state: 'error'; message: string };

const DASH = '-';

/** Their date, their way round: this page never sees a CRM user's locale. */
function requestDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return DASH;
  const d = String(parsed.getDate()).padStart(2, '0');
  const m = String(parsed.getMonth() + 1).padStart(2, '0');
  return `${d}/${m}/${parsed.getFullYear()}`;
}

function qty(value: number | null): string {
  if (value === null || value === undefined) return DASH;
  return new Intl.NumberFormat('en-US').format(value);
}

export default function PublicSupplierRequestPage({
  params,
}: {
  params: Promise<{ company: string; token: string }>;
}) {
  const { token } = use(params);
  const [status, setStatus] = useState<Status>({ state: 'loading' });
  const [downloading, setDownloading] = useState<'pdf' | 'xlsx' | null>(null);

  useEffect(() => {
    let live = true;

    readSupplierRequest(token)
      .then((request) => {
        if (live) setStatus({ state: 'ready', request });
      })
      .catch((error: unknown) => {
        if (!live) return;
        if (error instanceof SupplierRequestUnavailableError) {
          setStatus({ state: 'missing' });
          return;
        }
        setStatus({
          state: 'error',
          message: error instanceof Error ? error.message : 'Something went wrong.',
        });
      });

    return () => {
      live = false;
    };
  }, [token]);

  async function download(kind: 'pdf' | 'xlsx') {
    setDownloading(kind);
    try {
      const { url } = await readSupplierRequestDocument(token, kind);
      window.open(url, '_blank', 'noopener');
    } catch {
      // The page itself is still readable, so a failed download must not replace it.
      // Falling back to the state the reader can act on: try again.
      setDownloading(null);
      return;
    }
    setDownloading(null);
  }

  if (status.state === 'loading') {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-4 px-4 py-10 sm:px-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // Unknown, expired and superseded are ONE answer, here and on the server: saying
  // which would confirm to anybody guessing that a token exists.
  if (status.state === 'missing' || status.state === 'error') {
    return (
      <div className="mx-auto max-w-xl px-4 py-24 text-center">
        <h1 className="text-xl font-semibold text-foreground">
          此链接已失效 / This link is no longer available
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          请联系 Sorento 重新发送。 / Please ask your contact at Sorento to resend it.
        </p>
      </div>
    );
  }

  const { request } = status;

  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6 sm:py-10">
      <header className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold sm:text-xl">配柜要求 / Container request</h1>
          <p className="mt-1 break-words text-sm text-muted-foreground">
            {request.supplier_name}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            日期 / Date {requestDate(request.requested_at)} · 项目 / Items{' '}
            {request.line_count}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {request.has_pdf ? (
            <Button
              size="sm"
              variant="outline"
              disabled={downloading === 'pdf'}
              onClick={() => download('pdf')}
            >
              {downloading === 'pdf' ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <Download className="size-4" />
              )}
              PDF
            </Button>
          ) : null}
          {request.has_xlsx ? (
            <Button
              size="sm"
              variant="outline"
              disabled={downloading === 'xlsx'}
              onClick={() => download('xlsx')}
            >
              {downloading === 'xlsx' ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <Download className="size-4" />
              )}
              Excel
            </Button>
          ) : null}
        </div>
      </header>

      {request.lines.length === 0 ? (
        <p className="mt-8 rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          此要求没有项目。 / This request has no items.
        </p>
      ) : (
        <div className="mt-5 -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-start text-xs text-muted-foreground">
                <th className="py-2 pe-3 text-start font-medium">#</th>
                <th className="py-2 pe-3 text-start font-medium">型号 / Item</th>
                <th className="py-2 pe-3 text-start font-medium">品名 / Description</th>
                <th className="py-2 pe-3 text-end font-medium">需装数量 / Qty to load</th>
                <th className="py-2 pe-3 text-end font-medium">包装好库存 / Packed</th>
                <th className="py-2 text-end font-medium">空瓷 / Unfinished</th>
              </tr>
            </thead>
            <tbody>
              {request.lines.map((line, index) => (
                <tr key={`${line.item_code ?? index}-${index}`} className="border-b border-border">
                  <td className="py-2 pe-3 text-muted-foreground tabular-nums">{index + 1}</td>
                  <td className="py-2 pe-3 font-medium">{line.item_code ?? DASH}</td>
                  <td className="py-2 pe-3 text-muted-foreground">
                    {line.product_name ?? DASH}
                  </td>
                  <td className="py-2 pe-3 text-end font-semibold tabular-nums">
                    {qty(line.qty)}
                  </td>
                  <td className="py-2 pe-3 text-end tabular-nums text-muted-foreground">
                    {qty(line.qty_packed)}
                  </td>
                  <td className="py-2 text-end tabular-nums text-muted-foreground">
                    {qty(line.qty_unfinished)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
