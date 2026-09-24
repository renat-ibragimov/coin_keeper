import { Link, useLocation } from 'react-router-dom';

import { useAuthDialog } from '@/features/auth/authDialogContext';
import { useAuth } from '@/features/auth/useAuth';
import { Button } from '@/shared/ui';

export function GuestAddButton({
  itemId,
  children,
  backTo,
  size = 'md',
  block = false,
}: {
  itemId: number;
  children: React.ReactNode;
  backTo?: string;
  size?: 'sm' | 'md';
  block?: boolean;
}) {
  const { user } = useAuth();
  const location = useLocation();
  if (user) {
    return (
      <Link
        to={`/collection/add?catalogItemId=${itemId}`}
        state={{ from: backTo ?? location.pathname + location.search }}
      >
        <Button size={size} block={block}>
          {children}
        </Button>
      </Link>
    );
  }
  const from = backTo ?? location.pathname + location.search;
  return (
    <GuestAction from={from} itemId={itemId} size={size} block={block}>
      {children}
    </GuestAction>
  );
}

function GuestAction({
  from,
  itemId,
  size,
  block,
  children,
}: {
  from: string;
  itemId: number;
  size: 'sm' | 'md';
  block: boolean;
  children: React.ReactNode;
}) {
  const openAuth = useAuthDialog();
  return (
    <Button
      size={size}
      block={block}
      onClick={() =>
        openAuth('register', {
          from: `/collection/add?catalogItemId=${itemId}`,
          returnState: { from },
          purpose: 'collection',
        })
      }
    >
      {children}
    </Button>
  );
}
