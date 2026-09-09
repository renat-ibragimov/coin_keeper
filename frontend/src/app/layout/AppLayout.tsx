import {
  BarChart3,
  ChevronDown,
  Coins,
  Heart,
  Layers,
  LayoutGrid,
  LogOut,
  Settings,
  Shield,
  User,
  Wallet,
} from 'lucide-react';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { useDismissable } from '@/shared/lib/useDismissable';

import { Brand } from './Brand';
import { LocaleSwitcher, ThemeSwitcher } from './HeaderControls';
import styles from './AppLayout.module.css';

const COLLECTION_TABS = [
  { to: '/collection', key: 'nav.dashboard', end: true },
  { to: '/collection/coins', key: 'nav.coins', end: false },
  { to: '/collection/series', key: 'nav.series', end: false },
  { to: '/collection/money', key: 'nav.expenses', end: false },
] as const;

/** Outside "Моя колекція": just the two top-level places (docs/08-ui-map.md). */
const MOBILE_PLAIN = [
  { to: '/catalog', key: 'nav.catalog', end: false, icon: LayoutGrid },
  { to: '/collection', key: 'nav.myCollection', end: false, icon: Heart },
] as const;

/** Inside "Моя колекція": its own four sections plus the catalog, all one
 *  tap away — settings and admin moved into the account menu, so nothing
 *  here needs a "more" sheet to hold them any more. */
const MOBILE_COLLECTION = [
  { to: '/catalog', key: 'nav.catalog', end: false, icon: LayoutGrid },
  { to: '/collection', key: 'nav.dashboard', end: true, icon: BarChart3 },
  { to: '/collection/coins', key: 'nav.coins', end: false, icon: Coins },
  { to: '/collection/series', key: 'nav.series', end: false, icon: Layers },
  { to: '/collection/money', key: 'nav.expenses', end: false, icon: Wallet },
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
  const mobileLinks = inCollection ? MOBILE_COLLECTION : MOBILE_PLAIN;

  const [accountOpen, setAccountOpen] = useState(false);
  const accountMenu = useRef<HTMLDivElement>(null);
  const accountButton = useRef<HTMLButtonElement>(null);
  useDismissable(accountOpen, () => setAccountOpen(false), {
    inside: [accountMenu, accountButton],
  });
  const closeAccount = () => setAccountOpen(false);

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
          {/* Standalone on desktop, where there's room beside the avatar;
              folded into the account menu below on the phone instead
              (docs/08-ui-map.md). */}
          <div className={styles.headerSwitches}>
            <LocaleSwitcher />
            <ThemeSwitcher />
          </div>
          <div className={styles.account}>
            <button
              ref={accountButton}
              type="button"
              className={styles.accountButton}
              onClick={() => setAccountOpen((open) => !open)}
              aria-expanded={accountOpen}
              aria-label={t('account.menuLabel')}
            >
              <span className={styles.avatar} aria-hidden="true">
                <User size={16} />
              </span>
              <span className={styles.accountName}>{user?.displayName || user?.email}</span>
              <ChevronDown className={styles.accountChevron} size={15} aria-hidden="true" />
            </button>
            {accountOpen ? (
              <div ref={accountMenu} className={styles.accountMenu} role="menu">
                <div className={styles.accountMenuProfile}>
                  <span className={`${styles.avatar} ${styles.avatarLarge}`} aria-hidden="true">
                    <User size={20} />
                  </span>
                  <span className={styles.accountMenuProfileText}>
                    <span className={styles.accountMenuProfileName}>
                      {user?.displayName || user?.email}
                    </span>
                    {user?.displayName ? (
                      <span className={styles.accountMenuProfileEmail}>{user?.email}</span>
                    ) : null}
                  </span>
                </div>

                {/* Desktop shows these standalone in the header instead
                    (styles.headerSwitches above) — repeating them here too
                    would just be the same two controls twice on one screen. */}
                <div className={styles.accountMenuMobileOnly}>
                  <div className={styles.accountMenuRow}>
                    <span className={styles.accountMenuRowLabel}>{t('settings.locale')}</span>
                    <LocaleSwitcher />
                  </div>
                  <div className={styles.accountMenuRow}>
                    <span className={styles.accountMenuRowLabel}>{t('settings.theme')}</span>
                    <ThemeSwitcher />
                  </div>
                </div>

                <span className={styles.accountMenuDivider} aria-hidden="true" />

                <NavLink
                  to="/settings"
                  className={styles.accountMenuLink}
                  role="menuitem"
                  onClick={closeAccount}
                >
                  <Settings size={16} aria-hidden="true" />
                  {t('nav.settings')}
                </NavLink>
                {isAdmin ? (
                  <NavLink
                    to="/admin"
                    className={styles.accountMenuLink}
                    role="menuitem"
                    onClick={closeAccount}
                  >
                    <Shield size={16} aria-hidden="true" />
                    {t('nav.admin')}
                  </NavLink>
                ) : null}
                <button
                  type="button"
                  role="menuitem"
                  className={styles.accountMenuLink}
                  onClick={() => void signOut()}
                >
                  <LogOut size={16} aria-hidden="true" />
                  {t('header.logout')}
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {/* Everything below the header scrolls in here rather than in the
          window, so the scrollbar and its reserved gutter never reach the
          header — data-scroll-area is what shared/lib/pageScroll.ts steers by
          (docs/08-ui-map.md). On the phone layout the CSS hands scrolling
          back to the document. */}
      <div className={styles.scrollArea} data-scroll-area>
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
      </div>

      <nav className={styles.bottomNav} aria-label={t('nav.label')}>
        {mobileLinks.map((section) => (
          <NavLink
            key={section.to}
            to={section.to}
            end={section.end}
            className={navClass(styles.bottomLink, styles.bottomLinkActive)}
          >
            <section.icon size={19} aria-hidden="true" />
            {t(section.key)}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
