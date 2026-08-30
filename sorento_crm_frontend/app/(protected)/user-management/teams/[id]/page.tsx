import { Metadata } from 'next';
import Link from 'next/link';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { Button } from '@/components/ui/button';
import { ChevronLeft } from 'lucide-react';
import TeamMembersClient from './components/team-members-client';

export const metadata: Metadata = {
  title: 'Team members',
  description: 'Manage team members for round-robin.',
};

type Props = { params: Promise<{ id: string }> };

export default async function TeamMembersPage({ params }: Props) {
  const { id } = await params;
  return (
    <>
      <Container>
        <PageHeader
          title="Team members"
          actions={
            <Button variant="outline" size="sm" asChild>
              <Link href="/user-management/teams">
                <ChevronLeft className="me-1 size-4" />
                Back to teams
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <TeamMembersClient teamId={id} />
      </Container>
    </>
  );
}
