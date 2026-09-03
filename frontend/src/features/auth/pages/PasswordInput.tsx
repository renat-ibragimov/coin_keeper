import { useState } from 'react';
import type { ComponentProps } from 'react';
import { useTranslation } from 'react-i18next';

import { Input } from '@/shared/ui';

import styles from './authForms.module.css';

type PasswordInputProps = Omit<ComponentProps<typeof Input>, 'type'>;

export function PasswordInput(props: PasswordInputProps) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  return (
    <div className={styles.passwordField}>
      <Input {...props} type={visible ? 'text' : 'password'} />
      <button
        type="button"
        className={styles.passwordReveal}
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? t('auth.hidePassword') : t('auth.showPassword')}
      >
        {visible ? '◡' : '👁'}
      </button>
    </div>
  );
}
