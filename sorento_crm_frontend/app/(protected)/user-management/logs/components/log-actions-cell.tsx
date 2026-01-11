import { RiCheckboxCircleFill } from '@remixicon/react';
import { Row } from '@tanstack/react-table';
import { Ellipsis } from 'lucide-react';
import { toast } from 'sonner';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { SystemLog } from '@/app/models/system';

export const LogActionsCell = ({ row }: { row: Row<SystemLog> }) => {
  const { copyToClipboard } = useCopyToClipboard();
  const handleCopyUserId = () => {
    copyToClipboard(row.original.userId);
    const message = 'User ID copied to clipboard';
    toast.custom(
      (t) => (
        <Alert
          variant="mono"
          icon="success"
          close={false}
          onClose={() => toast.dismiss(t)}
        >
          <AlertIcon>
            <RiCheckboxCircleFill />
          </AlertIcon>
          <AlertTitle>{message}</AlertTitle>
        </Alert>
      ),
      {
        position: 'top-center',
      },
    );
  };

  const handleCopyEntityId = () => {
    copyToClipboard(row.original.entityId || '');
    const message = 'Entity ID copied to clipboard';
    toast.custom(
      (t) => (
        <Alert
          variant="mono"
          icon="success"
          close={false}
          onClose={() => toast.dismiss(t)}
        >
          <AlertIcon>
            <RiCheckboxCircleFill />
          </AlertIcon>
          <AlertTitle>{message}</AlertTitle>
        </Alert>
      ),
      {
        position: 'top-center',
      },
    );
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button className="h-7 w-7" mode="icon" variant="ghost">
          <Ellipsis />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="bottom" align="start">
        <DropdownMenuItem onClick={handleCopyEntityId}>
          Copy Entity ID
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleCopyUserId}>
          Copy User ID
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
