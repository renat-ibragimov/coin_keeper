import {
  ArrowRight,
  Check,
  ChevronRight,
  Coins,
  FolderPlus,
  LayoutGrid,
  Scale,
  Search,
  Table2,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { useAuthDialog } from '@/features/auth/authDialogContext';
import { useAuth } from '@/features/auth/useAuth';

import obverse from './assets/love-obverse.webp';
import reverse from './assets/love-reverse.webp';
import airAssaultObverse from './assets/air-assault-obverse.webp';
import airAssaultReverse from './assets/air-assault-reverse.webp';
import lesyaObverse from './assets/lesya-obverse.webp';
import lesyaReverse from './assets/lesya-reverse.webp';
import { landingCopy } from './copy';
import { ExpensesDemo } from './ExpensesDemo';
import type { LandingCopy } from './copy';
import styles from './LandingPage.module.css';

const demoSpecimens = [
  { price: 4200, delivery: 120, purchased: '2025-03-12', storage: 'album' },
  { price: 4450, delivery: 80, purchased: '2025-06-08', storage: 'capsule' },
] as const;
const demoMarketPrice = 5100;
const demoPurchaseTotal = demoSpecimens.reduce((sum, item) => sum + item.price + item.delivery, 0);
const sampleCoins = [
  {
    id: 0,
    year: 2025,
    seriesId: 23,
    obverse,
    reverse,
    count: 2,
    cost: demoPurchaseTotal,
    value: demoMarketPrice * 2,
    extra: 200,
    date: '2025-06-08',
  },
  {
    id: 1,
    year: 2021,
    seriesId: 13,
    obverse: airAssaultObverse,
    reverse: airAssaultReverse,
    count: 1,
    cost: 250,
    value: 310,
    extra: 30,
    date: '2025-05-20',
  },
  {
    id: 2,
    year: 1996,
    seriesId: 15,
    obverse: lesyaObverse,
    reverse: lesyaReverse,
    count: 3,
    cost: 1950,
    value: 2250,
    extra: 250,
    date: '2025-04-12',
  },
];

function money(value: number, en: boolean) {
  return `${new Intl.NumberFormat(en ? 'en-GB' : 'uk-UA').format(value)} ₴`;
}

function CoinPreview({ c, en }: { c: LandingCopy; en: boolean }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'instances' | 'details'>('instances');
  const marketTotal = demoMarketPrice * demoSpecimens.length;
  const valueChange = marketTotal - demoPurchaseTotal;
  const deliveryTotal = demoSpecimens.reduce((sum, item) => sum + item.delivery, 0);
  const changePercent = new Intl.NumberFormat(en ? 'en-GB' : 'uk-UA', {
    style: 'percent',
    maximumFractionDigits: 1,
    signDisplay: 'always',
  }).format(valueChange / demoPurchaseTotal);
  return (
    <div className={styles.coinPreview}>
      <div className={styles.previewTop}>
        <span>
          <span className={styles.statusDot} />
          {c.demo}
        </span>
        <span className={styles.owned}>
          <Check size={13} />
          {c.inCollection} · {demoSpecimens.length}
        </span>
      </div>
      <div className={styles.coinImages}>
        <img
          src={obverse}
          alt={`${c.coin} — ${en ? 'obverse' : 'аверс'}`}
          width="600"
          height="600"
          fetchPriority="high"
        />
        <img
          src={reverse}
          alt={`${c.coin} — ${en ? 'reverse' : 'реверс'}`}
          width="600"
          height="600"
          fetchPriority="high"
        />
      </div>
      <div className={styles.coinHeading}>
        <div>
          <p>{c.coinMeta}</p>
          <h2>{c.coin}</h2>
        </div>
        <div className={styles.marketQuote}>
          <span>{t('card.currentPrice')}</span>
          <strong>{money(demoMarketPrice, en)}</strong>
          <span>{c.perCoin}</span>
        </div>
      </div>
      <div className={styles.coinTags}>
        <span>{c.silver}</span>
        <span>{c.weight}</span>
        <span>НБУ</span>
      </div>
      <div className={styles.coinFinance}>
        <div>
          <span>{t('card.purchasedTotal')}</span>
          <strong>{money(demoPurchaseTotal, en)}</strong>
          <small>{t('card.supportingExpensesIncluded', { value: money(deliveryTotal, en) })}</small>
        </div>
        <div>
          <span>{t('card.currentValue')}</span>
          <strong>{money(marketTotal, en)}</strong>
          <small>
            {demoSpecimens.length} {c.specimensCount}
          </small>
        </div>
        <div className={styles.positiveChange}>
          <span>{t('card.valueChange')}</span>
          <strong>+{money(valueChange, en)}</strong>
          <small>{changePercent}</small>
        </div>
      </div>
      <div className={styles.tabs} role="tablist" aria-label={c.coin}>
        <button
          type="button"
          role="tab"
          id="coin-instances-tab"
          aria-controls="coin-instances-panel"
          aria-selected={tab === 'instances'}
          onClick={() => setTab('instances')}
        >
          {t('card.instances')}
          <span>2</span>
        </button>
        <button
          type="button"
          role="tab"
          id="coin-details-tab"
          aria-controls="coin-details-panel"
          aria-selected={tab === 'details'}
          onClick={() => setTab('details')}
        >
          {c.details}
        </button>
      </div>
      <div className={styles.coinPanel}>
        <div
          className={styles.specimenPanel}
          id="coin-instances-panel"
          role="tabpanel"
          aria-labelledby="coin-instances-tab"
          aria-hidden={tab !== 'instances'}
          inert={tab !== 'instances'}
        >
          <table className={styles.specimens}>
            <thead>
              <tr>
                <th scope="col">{t('card.instancePrice')}</th>
                <th scope="col">{t('card.instanceExtraExpenses')}</th>
                <th scope="col">{t('card.instanceFullPrice')}</th>
                <th scope="col">{t('card.instanceCurrentPrice')}</th>
                <th scope="col">{t('card.instanceChange')}</th>
                <th scope="col">{t('card.instanceStorage')}</th>
              </tr>
            </thead>
            <tbody>
              {demoSpecimens.map((item) => (
                <tr key={item.purchased}>
                  <td>
                    <strong>{money(item.price, en)}</strong>
                  </td>
                  <td>
                    <strong>{money(item.delivery, en)}</strong>
                  </td>
                  <td>
                    <strong>{money(item.price + item.delivery, en)}</strong>
                  </td>
                  <td>
                    <strong>{money(demoMarketPrice, en)}</strong>
                  </td>
                  <td className={styles.specimenChange}>
                    <strong>+{money(demoMarketPrice - item.price - item.delivery, en)}</strong>
                  </td>
                  <td>{c[item.storage]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div
          className={styles.coinDetails}
          id="coin-details-panel"
          role="tabpanel"
          aria-labelledby="coin-details-tab"
          aria-hidden={tab !== 'details'}
          inert={tab !== 'details'}
        >
          <p>{c.coinDescription}</p>
          <Link to="/catalog/3098">
            {c.coinLink}
            <ArrowRight size={15} />
          </Link>
        </div>
      </div>
    </div>
  );
}

function CollectionDemo({ c, en }: { c: LandingCopy; en: boolean }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [series, setSeries] = useState('');
  const [year, setYear] = useState('');
  const [view, setView] = useState<'cards' | 'table'>('table');
  const [sort, setSort] = useState('year');
  const coins = sampleCoins
    .filter(
      (coin) =>
        (!series || coin.seriesId === Number(series)) &&
        (!year || coin.year === Number(year)) &&
        c.demoNames[coin.id]!.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()),
    )
    .sort((a, b) =>
      sort === 'title'
        ? c.demoNames[a.id]!.localeCompare(c.demoNames[b.id]!, en ? 'en' : 'uk')
        : sort === 'cost'
          ? b.cost - a.cost
          : b.year - a.year,
    );
  const count = coins.reduce((sum, coin) => sum + coin.count, 0);
  const spent = coins.reduce((sum, coin) => sum + coin.cost, 0);
  const valuation = coins.reduce((sum, coin) => sum + coin.value, 0);
  const extra = coins.reduce((sum, coin) => sum + coin.extra, 0);
  const delta = valuation - spent;
  const stats = [
    {
      label: t('dashboard.tileCoins'),
      value: count,
      hint: t('dashboard.tileCoinsHint', { count: coins.length }),
      icon: Coins,
    },
    {
      label: t('dashboard.spentTotal'),
      value: money(spent, en),
      hint: t('dashboard.tileSpentHint', { amount: money(extra, en) }),
      icon: Wallet,
    },
    { label: t('dashboard.marketValue'), value: money(valuation, en), icon: TrendingUp },
    {
      label: t('dashboard.delta'),
      value: `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${money(Math.abs(delta), en)}`,
      hint:
        spent > 0
          ? new Intl.NumberFormat(en ? 'en-GB' : 'uk-UA', {
              style: 'percent',
              maximumFractionDigits: 1,
              signDisplay: 'always',
            }).format(delta / spent)
          : undefined,
      icon: Scale,
    },
  ];
  const filtered = Boolean(search || series || year);
  const reset = () => {
    setSearch('');
    setSeries('');
    setYear('');
  };
  const thumbnail = (coin: (typeof sampleCoins)[number]) => (
    <span className={styles.coinThumb}>
      <img
        src={coin.obverse}
        alt={`${c.demoNames[coin.id]} — ${en ? 'obverse' : 'аверс'}`}
        width="36"
        height="36"
        loading="lazy"
      />
    </span>
  );
  return (
    <div className={`${styles.demoFrame} ${styles.collectionDemo}`}>
      <div className={styles.collectionHeading}>
        <h3>{t('collection.title')}</h3>
        <p>{t('collection.subtitle')}</p>
      </div>
      <div className={styles.collectionMetrics} aria-live="polite">
        {stats.map(({ label, value, hint, icon: Icon }, index) => (
          <div key={label}>
            <Icon size={15} aria-hidden="true" />
            <div>
              <span>{label}</span>
              <strong
                className={
                  index === 3
                    ? delta < 0
                      ? styles.negativeValue
                      : delta > 0
                        ? styles.positiveValue
                        : undefined
                    : undefined
                }
              >
                {value}
              </strong>
              {hint && <small>{hint}</small>}
            </div>
          </div>
        ))}
      </div>
      <div className={styles.collectionFilters}>
        <label className={styles.search}>
          <Search size={14} />
          <input
            type="search"
            aria-label={t('collection.searchPlaceholder')}
            placeholder={t('collection.searchPlaceholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          <span>{t('catalog.tableSeries')}</span>
          <select value={series} onChange={(e) => setSeries(e.target.value)}>
            <option value="">{t('collection.allSeries')}</option>
            {sampleCoins.map((coin) => (
              <option key={coin.seriesId} value={coin.seriesId}>
                {c.demoSeries[coin.id]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{t('add.year')}</span>
          <select value={year} onChange={(e) => setYear(e.target.value)}>
            <option value="">{t('catalog.all')}</option>
            {sampleCoins.map((coin) => (
              <option key={coin.year} value={coin.year}>
                {coin.year}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className={styles.collectionToolbar}>
        <span aria-live="polite">
          {t('pagination.shown', { shown: coins.length, total: coins.length })}
        </span>
        {filtered && (
          <button type="button" className={styles.resetDemo} onClick={reset}>
            {t('catalog.resetFilters')}
          </button>
        )}
        <div className={styles.collectionViews}>
          <button type="button" aria-pressed={view === 'cards'} onClick={() => setView('cards')}>
            <LayoutGrid size={12} />
            {t('catalog.viewCards')}
          </button>
          <button type="button" aria-pressed={view === 'table'} onClick={() => setView('table')}>
            <Table2 size={12} />
            {t('catalog.viewTable')}
          </button>
        </div>
        <select
          aria-label={t('catalog.sort')}
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="year">{t('catalog.sortYear')}</option>
          <option value="title">{t('collection.sortTitle')}</option>
          <option value="cost">{t('collection.sortTotal')}</option>
        </select>
      </div>
      <div className={styles.collectionResults}>
        {coins.length === 0 ? (
          <div className={styles.empty}>
            <p>{t('catalog.emptyTitle')}</p>
            <button type="button" onClick={reset}>
              {t('catalog.resetFilters')}
            </button>
          </div>
        ) : (
          <>
            <div
              className={styles.collectionTableWrap}
              aria-hidden={view !== 'table'}
              inert={view !== 'table'}
            >
              <table className={styles.collectionTable}>
                <thead>
                  <tr>
                    {[
                      'catalog.tableCoin',
                      'collection.quantity',
                      'collection.spent',
                      'collection.valuation',
                      'collection.lastAcquisition',
                      'collection.grade',
                    ].map((key) => (
                      <th scope="col" key={key}>
                        {t(key)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {coins.map((coin) => (
                    <tr key={coin.id}>
                      <td>
                        <div className={styles.collectionCoin}>
                          {thumbnail(coin)}
                          <div>
                            <strong>{c.demoNames[coin.id]}</strong>
                            <span>{c.demoMetas[coin.id]}</span>
                          </div>
                        </div>
                      </td>
                      <td>{t('catalog.quantity', { count: coin.count })}</td>
                      <td>{money(coin.cost, en)}</td>
                      <td>{money(coin.value, en)}</td>
                      <td>
                        {new Intl.DateTimeFormat(en ? 'en-GB' : 'uk-UA', {
                          timeZone: 'UTC',
                        }).format(new Date(coin.date))}
                      </td>
                      <td>
                        <span className={styles.collectionGrade}>UNC</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div
              className={styles.collectionCards}
              aria-hidden={view !== 'cards'}
              inert={view !== 'cards'}
            >
              {coins.map((coin) => (
                <article key={coin.id}>
                  <div className={styles.collectionCardImages}>
                    <img
                      src={coin.obverse}
                      alt={`${c.demoNames[coin.id]} — ${en ? 'obverse' : 'аверс'}`}
                      width="600"
                      height="600"
                      loading="lazy"
                    />
                    <img
                      src={coin.reverse}
                      alt={`${c.demoNames[coin.id]} — ${en ? 'reverse' : 'реверс'}`}
                      width="600"
                      height="600"
                      loading="lazy"
                    />
                  </div>
                  <h4>{c.demoNames[coin.id]}</h4>
                  <p>{c.demoSeries[coin.id]}</p>
                  <p>{c.demoMetas[coin.id]} · UNC</p>
                  <dl>
                    {[
                      ['collection.quantity', t('catalog.quantity', { count: coin.count })],
                      ['collection.spent', money(coin.cost, en)],
                      ['collection.valuation', money(coin.value, en)],
                    ].map(([key, value]) => (
                      <div key={key}>
                        <dt>{t(key!)}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))}
                  </dl>
                </article>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function LandingPage() {
  const { i18n } = useTranslation();
  const en = i18n.language === 'en';
  const c = landingCopy[en ? 'en' : 'uk'];
  const { user } = useAuth();
  const navigate = useNavigate();
  const openAuth = useAuthDialog();
  const start = () =>
    user
      ? navigate('/collection')
      : openAuth('register', { purpose: 'collection', from: '/collection' });
  const featureLinks = [
    { icon: FolderPlus, href: '#collection' },
    { icon: Wallet, href: '#analytics' },
    { icon: Coins, href: '#start' },
  ];

  return (
    <div className={styles.landing}>
      <section className={styles.hero} aria-labelledby="landing-title">
        <div className={styles.heroInner}>
          <div className={styles.heroArt} aria-hidden="true" />
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>
              <span />
              {c.eyebrow}
            </p>
            <h1 id="landing-title">{c.title}</h1>
            <p className={styles.heroIntro}>{c.intro}</p>
            <div className={styles.actions}>
              <button type="button" className={styles.primaryButton} onClick={start}>
                {user ? c.open : c.start}
                <ArrowRight size={17} />
              </button>
              <Link className={styles.secondaryButton} to="/catalog">
                {c.explore}
              </Link>
            </div>
            <div className={styles.heroNotes}>
              {c.heroNotes.map((note) => (
                <span key={note}>
                  <Check size={14} />
                  {note}
                </span>
              ))}
            </div>
          </div>
          <div className={styles.heroProduct}>
            <CoinPreview c={c} en={en} />
          </div>
        </div>
      </section>
      <div className={styles.featureStrip}>
        {c.featureTitles.map((title, index) => {
          const { icon: Icon, href } = featureLinks[index]!;
          return (
            <a className={styles.feature} key={title} href={href}>
              <span className={styles.featureIcon}>
                <Icon size={23} strokeWidth={1.4} />
              </span>
              <div>
                <h2>{title}</h2>
                <p>{c.featureTexts[index]}</p>
              </div>
              <ChevronRight size={16} />
            </a>
          );
        })}
      </div>
      <section className={styles.sectionStage} id="collection" aria-labelledby="collection-title">
        <div className={`${styles.sectionArt} ${styles.collectionArt}`} aria-hidden="true" />
        <div className={`${styles.section} ${styles.collectionSection}`}>
          <div className={styles.collectionStory}>
            <div className={styles.sectionCopy}>
              <h2 id="collection-title">{c.collectionTitle}</h2>
              <p>{c.collectionText}</p>
              <ul>
                {c.collectionBullets.map((text) => (
                  <li key={text}>
                    <Check size={16} />
                    <span>{text}</span>
                  </li>
                ))}
              </ul>
              <span className={styles.tryHint}>
                {c.tryFilters}
                <ArrowRight size={17} />
              </span>
            </div>
          </div>
          <CollectionDemo c={c} en={en} />
        </div>
      </section>
      <div className={styles.sectionDivider} />
      <section className={styles.sectionStage} id="analytics" aria-labelledby="expenses-title">
        <div className={`${styles.sectionArt} ${styles.expensesArt}`} aria-hidden="true" />
        <div className={`${styles.section} ${styles.expensesSection}`}>
          <div className={styles.sectionCopy}>
            <h2 id="expenses-title">{c.expensesTitle}</h2>
            <p>{c.expensesText}</p>
            <ul>
              {c.expensesBullets.map((text) => (
                <li key={text}>
                  <Check size={16} />
                  <span>{text}</span>
                </li>
              ))}
            </ul>
            <span className={styles.tryHint}>
              {c.tryPeriod}
              <ArrowRight size={17} />
            </span>
          </div>
          <ExpensesDemo c={c} en={en} />
        </div>
      </section>
      <section className={styles.finalCta} id="start" aria-labelledby="start-title">
        <span className={styles.ctaOrnament}>
          <Coins size={25} strokeWidth={1} />
        </span>
        <p className={styles.eyebrow}>{c.finalEyebrow}</p>
        <h2 id="start-title">{c.finalTitle}</h2>
        <p>{c.finalText}</p>
        <button className={styles.primaryButton} type="button" onClick={start}>
          {user ? c.open : c.start}
          <ArrowRight size={17} />
        </button>
      </section>
    </div>
  );
}
