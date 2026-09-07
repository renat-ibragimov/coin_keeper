import { ChevronDown } from 'lucide-react';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { useDismissable } from '@/shared/lib/useDismissable';

import { Brand } from './Brand';
import { LocaleSwitcher, ThemeToggle } from './HeaderControls';
import styles from './AppLayout.module.css';

const COLLECTION_TABS = [
  { to: '/collection', key: 'nav.dashboard', end: true },
  { to: '/collection/coins', key: 'nav.coins', end: false },
  { to: '/collection/series', key: 'nav.series', end: false },
  { to: '/collection/money', key: 'nav.expenses', end: false },
] as const;

/** The bottom bar on the phone; the rest of "Моя колекція" lives in "Ще". */
const MOBILE_PRIMARY = [
  { to: '/collection', key: 'nav.dashboard', end: true },
  { to: '/collection/coins', key: 'nav.coins', end: false },
  { to: '/catalog', key: 'nav.catalog', end: false },
] as const;

const MOBILE_MORE = [
  { to: '/collection/series', key: 'nav.series' },
  { to: '/collection/money', key: 'nav.expenses' },
  { to: '/settings', key: 'nav.settings' },
] as const;

function navClass(base = '', active = '') {
  return ({ isActive }: { isActive: boolean }) => (isActive ? `${base} ${active}` : base);
}

export function AppLayout() {
  const { t } = useTranslation();
  const location = useLocation();
  const { user, signOut } = useAuth();
  const isAdmin = user?.role === 'admin';
  const inCollection =
    location.pathname === '/collection' || location.pathname.startsWith('/collection/');

  const [moreOpen, setMoreOpen] = useState(false);
  const moreSheet = useRef<HTMLDivElement>(null);
  const moreButton = useRef<HTMLButtonElement>(null);
  useDismissable(moreOpen, () => setMoreOpen(false), { inside: [moreSheet, moreButton] });

  const [accountOpen, setAccountOpen] = useState(false);
  const accountMenu = useRef<HTMLDivElement>(null);
  const accountButton = useRef<HTMLButtonElement>(null);
  useDismissable(accountOpen, () => setAccountOpen(false), {
    inside: [accountMenu, accountButton],
  });

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Brand to="/collection" />
        <nav className={styles.nav} aria-label={t('nav.label')}>
          <NavLink to="/catalog" className={navClass(styles.navLink, styles.navLinkActive)}>
            {t('nav.catalog')}
          </NavLink>
          <NavLink to="/collection" className={navClass(styles.navLink, styles.navLinkActive)}>
            {t('nav.myCollection')}
          </NavLink>
          {isAdmin ? (
            <>
              <span className={styles.navDivider} aria-hidden="true" />
              <NavLink to="/admin" className={navClass(styles.navLink, styles.navLinkActive)}>
                {t('nav.admin')}
              </NavLink>
            </>
          ) : null}
        </nav>
        <div className={styles.controls}>
          <LocaleSwitcher />
          <ThemeToggle />
          <div className={styles.account}>
            <button
              ref={accountButton}
              type="button"
              className={styles.accountButton}
              onClick={() => setAccountOpen((open) => !open)}
              aria-expanded={accountOpen}
              aria-label={t('account.menuLabel')}
            >
              <span className={styles.accountName}>{user?.displayName || user?.email}</span>
              <span className={styles.accountChevron} aria-hidden="true">
                <ChevronDown size={15} />
              </span>
            </button>
            {accountOpen ? (
              <div ref={accountMenu} className={styles.accountMenu} role="menu">
                <NavLink
                  to="/settings"
                  className={styles.accountMenuLink}
                  role="menuitem"
                  onClick={() => setAccountOpen(false)}
                >
                  {t('nav.settings')}
                </NavLink>
                <button
                  type="button"
                  role="menuitem"
                  className={styles.accountMenuLink}
                  onClick={() => void signOut()}
                >
                  {t('header.logout')}
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {inCollection ? (
        <nav className={styles.subnav} aria-label={t('nav.collectionLabel')}>
          {COLLECTION_TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              className={navClass(styles.subnavLink, styles.subnavLinkActive)}
            >
              {t(tab.key)}
            </NavLink>
          ))}
        </nav>
      ) : null}

      <main className={styles.main}>
        <Outlet />
      </main>

      <nav className={styles.bottomNav} aria-label={t('nav.label')}>
        {MOBILE_PRIMARY.map((section) => (
          <NavLink
            key={section.to}
            to={section.to}
            end={section.end}
            className={navClass(styles.bottomLink, styles.bottomLinkActive)}
            onClick={() => setMoreOpen(false)}
          >
            {t(section.key)}
          </NavLink>
        ))}
        <button
          ref={moreButton}
          type="button"
          className={[styles.bottomLink, moreOpen ? styles.bottomLinkActive : ''].join(' ')}
          onClick={() => setMoreOpen((open) => !open)}
          aria-expanded={moreOpen}
        >
          {t('nav.more')}
        </button>
      </nav>

      {moreOpen ? (
        <div ref={moreSheet} className={styles.moreSheet}>
          {MOBILE_MORE.map((section) => (
            <NavLink
              key={section.to}
              to={section.to}
              className={navClass(styles.moreLink, styles.moreLinkActive)}
              onClick={() => setMoreOpen(false)}
            >
              {t(section.key)}
            </NavLink>
          ))}
          {isAdmin ? (
            <NavLink
              to="/admin"
              className={navClass(styles.moreLink, styles.moreLinkActive)}
              onClick={() => setMoreOpen(false)}
            >
              {t('nav.admin')}
            </NavLink>
          ) : null}
          <button type="button" className={styles.moreLink} onClick={() => void signOut()}>
            {t('header.logout')}
          </button>
        </div>
      ) : null}
    </div>
  );
}
