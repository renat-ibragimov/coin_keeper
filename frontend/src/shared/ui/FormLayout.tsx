import type { ReactNode } from 'react';

import styles from './FormLayout.module.css';

/** Vertical stack of fields with the shared gap. */
export function FormStack({ children }: { children: ReactNode }) {
  return <div className={styles.stack}>{children}</div>;
}

/** Two fields side by side on wide screens, stacked on phones. */
export function FormRow({ children }: { children: ReactNode }) {
  return <div className={styles.row}>{children}</div>;
}

export function FormSection({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {children}
    </section>
  );
}

export function FormActions({ children }: { children: ReactNode }) {
  return <div className={styles.actions}>{children}</div>;
}

export function FormError({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <div className={styles.error} role="alert">
      {children}
    </div>
  );
}
