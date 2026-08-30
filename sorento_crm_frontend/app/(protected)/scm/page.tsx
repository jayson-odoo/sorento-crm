import { Metadata } from 'next';
import Link from 'next/link';
import { ClipboardList } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { ScmDashboard } from './components/ScmDashboard';

export const metadata: Metadata = {
  title: 'Supply Chain Dashboard',
  description: 'Net position, stock valuation and warehouse health.',
};

export default function ScmDashboardPage() {
  return (
    <>
      <Container width="fluid">
        <PageHeader
          title="Supply Chain"
          actions={
            <>
              {/* M8-B6: header nav to the reorder planning page (daily cron + Manual
                  plan live there now). Navigates only - no inline run. */}
              <Button asChild>
                <Link href="/scm/reorder">
                  <ClipboardList className="size-4" />
                  Reorder plan
                </Link>
              </Button>
            </>
          }
        />
      </Container>

      <Container width="fluid">
        <ScmDashboard />
      </Container>
    </>
  );
}
