import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Button, Card, PageHeader } from '@/shared/ui';

export function GuestCollectionPage() {
  const { t } = useTranslation();
  return (
    <div style={{ maxWidth: 760, margin: '0 auto', width: '100%' }}>
      <PageHeader align="center" title={t('nav.myCollection')} />
      <nav
        aria-label={t('nav.collectionLabel')}
        style={{
          display: 'flex',
          justifyContent: 'center',
          gap: 20,
          marginBottom: 24,
          flexWrap: 'wrap',
        }}
      >
        {(['dashboard', 'coins', 'series', 'expenses'] as const).map((key) => (
          <span key={key}>{t(`nav.${key}`)}</span>
        ))}
      </nav>
      <Card>
        <h2>{t('guest.collectionTitle')}</h2>
        <p>{t('guest.collectionText')}</p>
        <ul>
          <li>{t('guest.saveCoins')}</li>
          <li>{t('guest.manageInstances')}</li>
          <li>{t('guest.followProgress')}</li>
          <li>{t('guest.trackFinance')}</li>
        </ul>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 24 }}>
          <Link to="/register" state={{ from: '/collection' }}>
            <Button>{t('guest.createCollection')}</Button>
          </Link>
          <Link to="/login" state={{ from: '/collection' }}>
            <Button variant="secondary">{t('guest.login')}</Button>
          </Link>
        </div>
      </Card>
    </div>
  );
}
