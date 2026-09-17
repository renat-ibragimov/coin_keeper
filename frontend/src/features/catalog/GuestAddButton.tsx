import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { Button, Modal } from '@/shared/ui';

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
  const { t } = useTranslation();
  const location = useLocation();
  const [open, setOpen] = useState(false);
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
    <>
      <Button size={size} block={block} onClick={() => setOpen(true)}>
        {children}
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={t('guest.addTitle')}
        size="sm"
        footer={
          <>
            <Link to="/register" state={{ from }} onClick={() => setOpen(false)}>
              <Button>{t('guest.register')}</Button>
            </Link>
            <Link to="/login" state={{ from }} onClick={() => setOpen(false)}>
              <Button variant="secondary">{t('guest.login')}</Button>
            </Link>
          </>
        }
      >
        <p>{t('guest.addText')}</p>
      </Modal>
    </>
  );
}
