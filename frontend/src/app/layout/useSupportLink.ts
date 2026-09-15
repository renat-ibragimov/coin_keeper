import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { api } from '@/shared/api/client';
import { useToast } from '@/shared/ui';

export function useSupportLink() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const location = useLocation();
  const toast = useToast();
  const [openingSupport, setOpeningSupport] = useState(false);

  const openSupport = async () => {
    if (openingSupport) return;
    setOpeningSupport(true);
    const telegramWindow = window.open('', '_blank');
    if (telegramWindow) telegramWindow.opener = null;
    try {
      const result = user
        ? await api<{ url: string }>('/support/telegram/link', {
            method: 'POST',
            body: { sourcePath: `${location.pathname}${location.search}` },
          })
        : await api<{ url: string }>('/support/telegram', { auth: false });
      if (telegramWindow) telegramWindow.location.href = result.url;
      else window.location.href = result.url;
    } catch {
      telegramWindow?.close();
      toast.show(t('footer.supportUnavailable'), 'error');
    } finally {
      setOpeningSupport(false);
    }
  };

  return { openSupport, openingSupport };
}
