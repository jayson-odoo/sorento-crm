'use client';

/**
 * The facts of a complaint, shown as the kind of complaint it actually is.
 *
 * One entity, two audiences. A complaint lodged through the consumer portal has a Site
 * address, a pin and a receipt; a project complaint has a Delivery Order Number, a
 * customer type, a salesperson and a project title. Before this split every case showed
 * both sets, so a retail complaint opened as a page of dashes and a dash could not be
 * read: "blank because this is retail" looked exactly like "blank because nobody filled
 * it in".
 *
 * The split is here and nowhere else. `complaintAudience` decides, the edit form and the
 * list read the same rule, and no component gets its own copy of the conditional.
 *
 * Everything universal - the fault, the products, the status - is rendered once for both.
 */
import Link from 'next/link';
import { ExternalLink, MapPin } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { formatDate } from '@/lib/helpers';

import {
  complaintAudience,
  pinMapsUrl,
  reportedByLabel,
  siteAddressLines,
} from '../lib/complaintAudience';
import type { Complaint, ComplaintProductLine } from '../types/complaint.types';

function Field({
  label,
  value,
  className,
}: {
  label: string;
  value: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="font-medium break-words">{value ?? '-'}</div>
    </div>
  );
}

/** The lines, from whichever source has them.
 *
 * `product_lines` is the source of truth. The CSV fallback exists for the rows written
 * before lines did, where `product_code` / `product_type` / `quantity` are three
 * index-aligned comma-separated columns. It is never used for a retail complaint, which
 * always writes lines.
 */
function resolveLines(complaint: Complaint): ComplaintProductLine[] {
  if (complaint.product_lines && complaint.product_lines.length > 0) {
    return complaint.product_lines;
  }
  return (complaint.product_code || '')
    .split(',')
    .map((code) => code.trim())
    .filter(Boolean)
    .map((code, i) => ({
      product_code: code,
      product_type: (complaint.product_type || '').split(',')[i]?.trim() || null,
      quantity: (complaint.quantity || '').split(',')[i]?.trim() || null,
    }));
}

function ProductLinesTable({
  lines,
  retail,
}: {
  lines: ComplaintProductLine[];
  retail: boolean;
}) {
  if (lines.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No products recorded on this complaint yet.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            {/* What the consumer said comes first on a retail case: the code beside it is
                frequently a guess, because SRTWC8152 matches three real variants and
                resolves to none of them. */}
            {retail && <th className="px-3 py-2 text-left">Reported as</th>}
            <th className="px-3 py-2 text-left">Product code</th>
            {retail ? (
              <>
                <th className="px-3 py-2 text-left">Matched product</th>
                <th className="px-3 py-2 text-left">Kind</th>
                <th className="px-3 py-2 text-left">Defect</th>
                <th className="px-3 py-2 text-left">Purchase</th>
              </>
            ) : (
              <th className="px-3 py-2 text-left">Product type</th>
            )}
            <th className="w-20 px-3 py-2 text-left">Qty</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line, i) => (
            <tr key={line.product_code + i} className="border-t align-top">
              {retail && (
                <td className="px-3 py-2">
                  <span title={line.claimed_text || undefined}>
                    {line.claimed_text || '-'}
                  </span>
                  {line.fault_description && (
                    <p className="mt-0.5 text-xs text-muted-foreground whitespace-pre-wrap">
                      {line.fault_description}
                    </p>
                  )}
                </td>
              )}
              <td className="px-3 py-2 font-medium">{line.product_code}</td>
              {retail ? (
                <>
                  <td className="px-3 py-2">{line.product_name || '-'}</td>
                  <td className="px-3 py-2">{line.kind_name || '-'}</td>
                  <td className="px-3 py-2">{line.defect_type_name || '-'}</td>
                  <td className="px-3 py-2">
                    {line.purchase_number ? (
                      <>
                        <span className="font-medium">{line.purchase_number}</span>
                        {line.purchase_date && (
                          <p className="text-xs text-muted-foreground">
                            {formatDate(new Date(line.purchase_date))}
                          </p>
                        )}
                      </>
                    ) : (
                      // "Not matched", never "no receipt". The consumer very often DID
                      // upload one - it is in Linked Attachments below - and what is
                      // missing is the purchase RECORD this line's cover computes from,
                      // because the date could not be read or the product did not resolve
                      // to a warranty kind. Telling CS there is no receipt when one is on
                      // the page sends them looking for a file they already have.
                      <span className="text-muted-foreground">Not matched</span>
                    )}
                  </td>
                </>
              ) : (
                <td className="px-3 py-2">{line.product_type || '-'}</td>
              )}
              <td className="px-3 py-2">{line.quantity || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SiteSection({ complaint }: { complaint: Complaint }) {
  const addressLines = siteAddressLines(complaint);
  const mapsUrl = pinMapsUrl(complaint.latitude, complaint.longitude);
  return (
    <div className="rounded-md border p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">Site</p>
          {addressLines.length > 0 ? (
            <div className="font-medium">
              {addressLines.map((line) => (
                <p key={line} className="break-words">
                  {line}
                </p>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No site address was captured. Ask the customer where the item is installed
              before dispatching anyone.
            </p>
          )}
        </div>
        {mapsUrl && (
          <Link
            href={mapsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex shrink-0 items-center gap-1 text-sm text-primary hover:underline"
          >
            <MapPin className="size-4" />
            Open pin
            <ExternalLink className="size-3" />
          </Link>
        )}
      </div>
      {/* The coordinates themselves are deliberately NOT printed. Nobody reads a lat/lng
          off a screen and nobody can correct one by hand; the "Open pin" link above is
          the whole of what a dispatcher does with it. */}
      {(complaint.site_contact_name || complaint.site_contact_phone) && (
        <p className="mt-2 text-sm">
          <span className="text-muted-foreground">Contact on site: </span>
          {[complaint.site_contact_name, complaint.site_contact_phone]
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}
    </div>
  );
}

export function ComplaintFieldGrid({ complaint }: { complaint: Complaint }) {
  const retail = complaintAudience(complaint) === 'retail';
  const lines = resolveLines(complaint);
  const complaintDate = complaint.complaint_date
    ? formatDate(new Date(complaint.complaint_date))
    : '-';

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {retail ? (
          <>
            <Field
              label="Reported by"
              value={reportedByLabel(complaint.reported_by_role)}
            />
            <Field label="Reported on" value={complaintDate} />
            <Field label="Customer" value={complaint.customer_name} />
            <Field label="Contact person" value={complaint.contact_person} />
            <Field label="Contact number" value={complaint.contact_number} />
            <Field label="Within warranty" value={complaint.within_warranty} />
          </>
        ) : (
          <>
            <Field
              label="Delivery Order Number"
              value={complaint.delivery_order_number}
            />
            <Field label="Complaint Date" value={complaintDate} />
            <Field label="Customer Type" value={complaint.customer_type} />
            {complaint.customer_type_others && (
              <Field
                label="Customer Type (Other)"
                value={complaint.customer_type_others}
              />
            )}
            <Field label="Within Warranty" value={complaint.within_warranty} />
            <Field label="Defects Discovered" value={complaint.defects_discovered} />
            <Field
              label="Complaint Type"
              value={
                complaint.complaint_type ? (
                  <Badge variant="secondary">{complaint.complaint_type}</Badge>
                ) : (
                  '-'
                )
              }
            />
            <Field label="Salesperson" value={complaint.salesperson} />
            <Field label="Customer Name" value={complaint.customer_name} />
            <Field label="Contact Person" value={complaint.contact_person} />
            <Field label="Contact Number" value={complaint.contact_number} />
            <Field label="Project Title" value={complaint.project_title} />
          </>
        )}

        <div className="md:col-span-2">
          <p className="text-sm text-muted-foreground mb-1">Products</p>
          <ProductLinesTable lines={lines} retail={retail} />
        </div>
      </div>

      {/* Always rendered, empty state and all: a section that disappears on missing data
          reads as "this case has no site", which is the opposite of what it means. */}
      {retail && <SiteSection complaint={complaint} />}

      {!retail && complaint.customer_address && (
        <Field label="Delivery Address" value={complaint.customer_address} />
      )}

      {complaint.defect_description && (
        <div>
          <p className="text-sm text-muted-foreground">
            {retail ? 'What the customer told us' : 'Defect Description'}
          </p>
          <p className="font-medium whitespace-pre-wrap">{complaint.defect_description}</p>
        </div>
      )}

      {/* The burst verbatim, in the order it was sent. Separate from the description
          above, which holds what the extractor MADE of it: folding them together loses
          the ability to tell a bad extraction from a badly-worded message. */}
      {retail && complaint.intake_transcript && (
        <details className="rounded-md border p-3">
          <summary className="cursor-pointer text-sm text-muted-foreground">
            Original message
          </summary>
          <p className="mt-2 text-sm whitespace-pre-wrap">{complaint.intake_transcript}</p>
        </details>
      )}
    </>
  );
}

export default ComplaintFieldGrid;
