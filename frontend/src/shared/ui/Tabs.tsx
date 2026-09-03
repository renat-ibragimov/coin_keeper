import type { ReactNode } from 'react';

import styles from './Tabs.module.css';

export interface TabOption<T extends string> {
  value: T;
  label: ReactNode;
}

interface TabsProps<T extends string> {
  options: TabOption<T>[];
  value: T;
  onChange: (value: T) => void;
  'aria-label'?: string;
}

export function Tabs<T extends string>({ options, value, onChange, ...rest }: TabsProps<T>) {
  return (
    <div className={styles.tabs} role="tablist" aria-label={rest['aria-label']}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={option.value === value}
          className={[styles.tab, option.value === value ? styles.active : ''].join(' ')}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
