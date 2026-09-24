import { ChevronLeft, ChevronRight, Coins, Layers, TrendingUp, Wallet } from 'lucide-react';
import { useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import love from '@/features/landing/assets/love-obverse.webp';
import lesya from '@/features/landing/assets/lesya-obverse.webp';
import { formatDate, formatMonthShort, formatUah } from '@/shared/lib/format';

import styles from './CollectionOnboarding.module.css';

export type CollectionSection = 'dashboard' | 'coins' | 'completeness' | 'money';
const slides = {
  dashboard: ['summary', 'value', 'progress'],
  coins: ['coins', 'filters', 'instances'],
  completeness: ['groups', 'progress', 'missing'],
  money: ['spending', 'chart', 'journal'],
} as const;
type Preview = (typeof slides)[CollectionSection][number];

/** Illustrated examples only: they never read or change a collector's data. */
export function CollectionOnboarding({
  section,
  actions,
}: {
  section: CollectionSection;
  actions: ReactNode;
}) {
  // A section change starts its own introduction, including guest route reuse.
  return <OnboardingSlides key={section} section={section} actions={actions} />;
}

function OnboardingSlides({
  section,
  actions,
}: {
  section: CollectionSection;
  actions: ReactNode;
}) {
  const { t } = useTranslation();
  const [active, setActive] = useState(0);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const id = useId();
  const items = slides[section];
  const move = (direction: number) =>
    setActive((current) => (current + direction + items.length) % items.length);

  return (
    <section className={styles.card} aria-label={t(`onboarding.${section}.heading`)}>
      <header className={styles.header}>
        <h2>{t(`onboarding.${section}.heading`)}</h2>
        <span className={styles.badge}>{t('onboarding.example')}</span>
      </header>
      <div
        className={styles.slides}
        id={`${id}-slides`}
        onTouchStart={(event) => {
          const touch = event.touches[0];
          touchStart.current = touch ? { x: touch.clientX, y: touch.clientY } : null;
        }}
        onTouchCancel={() => {
          touchStart.current = null;
        }}
        onTouchEnd={(event) => {
          const start = touchStart.current;
          touchStart.current = null;
          const end = event.changedTouches[0];
          if (!start || !end) return;
          const dx = end.clientX - start.x;
          const dy = end.clientY - start.y;
          if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) move(dx < 0 ? 1 : -1);
        }}
      >
        {items.map((preview, index) => (
          <div
            key={preview}
            className={styles.slide}
            aria-hidden={index !== active}
            inert={index !== active}
          >
            <div className={styles.preview}>
              <Example preview={preview} />
            </div>
            <div className={styles.caption}>
              <h3>{t(`onboarding.${section}.slides.${index}.title`)}</h3>
              <p>{t(`onboarding.${section}.slides.${index}.text`)}</p>
            </div>
          </div>
        ))}
      </div>
      <div
        className={styles.navigation}
        role="group"
        aria-label={t('onboarding.navigation')}
        onKeyDown={(event) => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          if (event.key === 'Home') setActive(0);
          else if (event.key === 'End') setActive(items.length - 1);
          else move(event.key === 'ArrowRight' ? 1 : -1);
        }}
      >
        <button
          type="button"
          onClick={() => move(-1)}
          aria-label={t('onboarding.previous')}
          aria-controls={`${id}-slides`}
        >
          <ChevronLeft size={18} aria-hidden="true" />
        </button>
        <div className={styles.dots}>
          {items.map((_, index) => (
            <button
              key={index}
              type="button"
              aria-label={t('onboarding.goTo', { number: index + 1 })}
              aria-current={index === active ? 'step' : undefined}
              aria-controls={`${id}-slides`}
              onClick={() => setActive(index)}
            >
              <span />
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => move(1)}
          aria-label={t('onboarding.next')}
          aria-controls={`${id}-slides`}
        >
          <ChevronRight size={18} aria-hidden="true" />
        </button>
      </div>
      <span className={styles.srOnly} aria-live="polite" aria-atomic="true">
        {t('onboarding.position', { number: active + 1, total: items.length })}.{' '}
        {t(`onboarding.${section}.slides.${active}.title`)}
      </span>
      <div className={styles.actions}>{actions}</div>
    </section>
  );
}

function Example({ preview }: { preview: Preview }) {
  const { t, i18n } = useTranslation();
  const money = (amount: number) => formatUah(amount, i18n.language);
  const row = (label: string, value: ReactNode) => (
    <div className={styles.row} key={label}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
  const coin = (image: string, name: string, value: string) => (
    <div className={styles.coinRow} key={name}>
      <img src={image} alt="" width="48" height="48" />
      <div>
        <strong>{name}</strong>
        <span>{value}</span>
      </div>
    </div>
  );

  switch (preview) {
    case 'summary':
    case 'spending': {
      const stats =
        preview === 'summary'
          ? ([
              [Coins, 'dashboard.tileCoins', '6'],
              [Wallet, 'dashboard.spentTotal', money(11050)],
              [TrendingUp, 'dashboard.marketValue', money(12760)],
            ] as const)
          : ([
              [Wallet, 'expenses.tileTotal', money(11050)],
              [Coins, 'expenses.tileCoins', money(10570)],
              [Layers, 'expenses.tileRelated', money(480)],
            ] as const);
      return (
        <div className={styles.metrics}>
          {stats.map(([Icon, label, value]) => (
            <div key={label}>
              <Icon size={20} aria-hidden="true" />
              <strong>{value}</strong>
              <span>{t(label)}</span>
            </div>
          ))}
        </div>
      );
    }
    case 'value':
      return (
        <div className={styles.rows}>
          {row(t('dashboard.spentTotal'), money(11050))}
          {row(t('dashboard.marketValue'), money(12760))}
          {row(t('dashboard.delta'), <span className={styles.positive}>+{money(1710)}</span>)}
        </div>
      );
    case 'progress':
      return (
        <div className={styles.progressExample}>
          <div className={styles.row}>
            <strong>{t('onboarding.seriesName')}</strong>
            <span>{t('onboarding.ownedCount', { owned: 7, total: 20 })}</span>
          </div>
          <div
            className={styles.progress}
            role="meter"
            aria-label={t('onboarding.seriesName')}
            aria-valuemin={0}
            aria-valuemax={20}
            aria-valuenow={7}
          >
            <span />
          </div>
          <div className={styles.row}>
            <span>{t('onboarding.remaining', { count: 13 })}</span>
            <strong>35%</strong>
          </div>
        </div>
      );
    case 'coins':
      return (
        <div className={styles.rows}>
          {coin(love, t('onboarding.love'), t('catalog.quantity', { count: 2 }))}
          {coin(lesya, t('onboarding.lesya'), t('catalog.quantity', { count: 3 }))}
        </div>
      );
    case 'filters':
      return (
        <div className={styles.filterExample}>
          <div className={styles.chips}>
            <span>{t('catalog.tableSeries')}</span>
            <span>{t('add.year')}: 2025</span>
            <span>{t('collection.sortTitle')}</span>
          </div>
          {coin(love, t('onboarding.love'), t('catalog.quantity', { count: 2 }))}
        </div>
      );
    case 'instances':
      return (
        <div className={styles.rows}>
          {row(t('onboarding.specimen', { number: 1 }), money(4200))}
          {row(t('onboarding.specimen', { number: 2 }), money(4450))}
          {row(t('card.instanceStorage'), t('onboarding.storage'))}
        </div>
      );
    case 'groups':
      return (
        <div className={styles.groupExample}>
          <div className={styles.chips}>
            {['Series', 'Year', 'Material'].map((key) => (
              <span key={key}>{t(`completeness.groupBy${key}`)}</span>
            ))}
          </div>
          {row(t('onboarding.seriesName'), t('onboarding.ownedCount', { owned: 7, total: 20 }))}
          {row(t('onboarding.anotherSeries'), t('onboarding.ownedCount', { owned: 4, total: 12 }))}
        </div>
      );
    case 'missing':
      return (
        <div className={styles.rows}>
          {row(t('onboarding.remainingLabel'), t('onboarding.coinCount', { count: 13 }))}
          {row(t('dashboard.missingBudget'), money(5200))}
          <p className={styles.note}>{t('onboarding.availablePrices')}</p>
        </div>
      );
    case 'chart':
      return (
        <div className={styles.chart} role="img" aria-label={t('onboarding.chartDescription')}>
          {[4320, 1920, 280, 4530].map((amount, index) => (
            <div className={styles.barColumn} key={index}>
              <span>{money(amount)}</span>
              <div className={styles.barTrack}>
                <div style={{ height: `${(amount / 4530) * 100}%` }} />
              </div>
              <span>{formatMonthShort(`2025-0${index + 3}`, i18n.language)}</span>
            </div>
          ))}
        </div>
      );
    case 'journal':
      return (
        <div className={styles.rows}>
          {row(t('expenses.categories.coin_purchase'), money(4450))}
          {row(t('expenses.categories.delivery'), money(80))}
          <p className={styles.note}>
            {t('onboarding.love')} · {formatDate('2025-06-08', i18n.language)}
          </p>
        </div>
      );
  }
}
