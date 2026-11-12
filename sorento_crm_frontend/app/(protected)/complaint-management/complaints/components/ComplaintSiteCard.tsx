import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SITE_FIELDS, type SiteFieldKey } from '../lib/siteFields';

export default function ComplaintSiteCard({
  complaint,
}: {
  complaint: Partial<Record<SiteFieldKey, string | null>>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Site</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          {SITE_FIELDS.map((f) => (
            <div key={f.key}>
              <dt className="text-sm text-muted-foreground">{f.label}</dt>
              <dd className="font-medium break-words">{complaint[f.key]?.trim() || '-'}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
