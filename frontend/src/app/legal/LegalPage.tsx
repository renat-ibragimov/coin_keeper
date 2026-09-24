import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Brand } from '@/app/layout/Brand';
import { LocaleSwitcher, ThemeSwitcher } from '@/app/layout/HeaderControls';
import { SiteFooter } from '@/app/layout/SiteFooter';
import { useAuth } from '@/features/auth/useAuth';

import { legalCopy } from './copy';
import styles from './LegalPage.module.css';

export function LegalPage({ kind }: { kind: 'privacy' | 'terms' }) {
  const { i18n } = useTranslation();
  const { user } = useAuth();
  const copy = legalCopy[i18n.language === 'en' ? 'en' : 'uk'][kind];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Brand to={user ? '/collection' : '/'} />
        <div className={styles.controls}>
          <LocaleSwitcher />
          <ThemeSwitcher />
        </div>
      </header>
      <main className={styles.main}>
        <nav className={styles.backNav} aria-label={copy.navigation}>
          <Link to={user ? '/collection' : '/'}>{copy.back}</Link>
          <span aria-hidden="true">·</span>
          <Link to={kind === 'privacy' ? '/terms' : '/privacy'}>{copy.other}</Link>
        </nav>
        <article className={styles.article}>
          <p className={styles.eyebrow}>Bakost Numismatics</p>
          <h1>{copy.title}</h1>
          <p className={styles.updated}>{copy.updated}</p>
          <p className={styles.intro}>{copy.intro}</p>
          {copy.sections.map((section) => (
            <section key={section.title}>
              <h2>{section.title}</h2>
              {section.paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </section>
          ))}
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
