import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Button, EmptyState } from '@/shared/ui';

export function ComingSoon({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return (
    <EmptyState
      title={t(titleKey)}
      description={t('common.comingSoon')}
      icon="⏳"
      actions={
        <Link to="/catalog">
          <Button variant="secondary">{t('common.backToCatalog')}</Button>
        </Link>
      }
    />
  );
}
