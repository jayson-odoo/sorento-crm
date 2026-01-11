import { Metadata } from 'next';
import { Container } from '@/components/common/container';
/*
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';*/
import LogList from './components/log-list';

export const metadata: Metadata = {
  title: 'Logs',
  description: 'Logs',
};

export default async function ActivityLogsPage() {
  return (
    <>
      {/*
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Logs</ToolbarTitle>
          </ToolbarHeading>
          <ToolbarActions></ToolbarActions>
        </Toolbar>
      </Container>
      */}
      <Container>
        <LogList />
      </Container>
    </>
  );
}
