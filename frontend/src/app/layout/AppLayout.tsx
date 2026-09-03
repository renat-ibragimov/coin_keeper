import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { Button } from '@/shared/ui';

import { Brand } from './Brand';
import { LocaleSwitcher, ThemeToggle } from './HeaderControls';
import styles from './AppLayout.module.css';

const SECTIONS = [
  { to: '/dashboard', key: 'nav.dashboard' },
  { to: '/catalog', key: 'nav.catalog' },
  { to: '/series', key: 'nav.series' },
  { to: '/collection', key: 'nav.collection' },
  { to: '/missing', key: 'nav.missing' },
  { to: '/settings', key: 'nav.settings' },
] as const;

/** The first tabs live in the mobile bottom bar; the rest go into "More". */
const MOBILE_PRIMARY = ['/dashboard', '/catalog', '/collection'];

function navClass(base = '', active = '') {
  return ({ isActive }: { isActive: boolean }) => (isActive ? `${base} ${active}` : base);
}

export function AppLayout() {
  const { t } = useTranslation();
  const { user, signOut } = useAuth();
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Brand />
        <nav className={styles.nav} aria-label={t('nav.label')}>
          {SECTIONS.map((section) => (
            <NavLink
              key={section.to}
              to={section.to}
              className={navClass(styles.navLink, styles.navLinkActive)}
            >
              {t(section.key)}
            </NavLink>
          ))}
        </nav>
        <div className={styles.controls}>
          <LocaleSwitcher />
          <ThemeToggle />
          <div className={styles.user}>
            <span className={styles.userName}>{user?.displayName || user?.email}</span>
            <Button variant="ghost" size="sm" onClick={() => void signOut()}>
              {t('header.logout')}
            </Button>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        <Outlet />
      </main>

      <nav className={styles.bottomNav} aria-label={t('nav.label')}>
        {SECTIONS.filter((section) => MOBILE_PRIMARY.includes(section.to)).map((section) => (
          <NavLink
            key={section.to}
            to={section.to}
            className={navClass(styles.bottomLink, styles.bottomLinkActive)}
            onClick={() => setMoreOpen(false)}
          >
            {t(section.key)}
          </NavLink>
        ))}
        <button
          type="button"
          className={[styles.bottomLink, moreOpen ? styles.bottomLinkActive : ''].join(' ')}
          onClick={() => setMoreOpen((open) => !open)}
          aria-expanded={moreOpen}
        >
          {t('nav.more')}
        </button>
      </nav>

      {moreOpen ? (
        <div className={styles.moreSheet}>
          {SECTIONS.filter((section) => !MOBILE_PRIMARY.includes(section.to)).map((section) => (
            <NavLink
              key={section.to}
              to={section.to}
              className={navClass(styles.moreLink, styles.moreLinkActive)}
              onClick={() => setMoreOpen(false)}
            >
              {t(section.key)}
            </NavLink>
          ))}
          <button type="button" className={styles.moreLink} onClick={() => void signOut()}>
            {t('header.logout')}
          </button>
        </div>
      ) : null}
    </div>
  );
}
