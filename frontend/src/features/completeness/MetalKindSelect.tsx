import { useTranslation } from 'react-i18next';

import type { MetalKind } from '@/shared/api/types';
import { Select } from '@/shared/ui';

import styles from './MetalKindSelect.module.css';

interface MetalKindSelectProps {
  value: MetalKind | undefined;
  onChange: (value: MetalKind | null) => void;
}

/** The Комплектність metal-kind filter, shared by the group list and a
 * group's own detail screen: the closed trigger names the pick once one is
 * made, but stacks it over its own (longest) default label -- invisible,
 * same grid cell -- so the trigger's width never shrinks below that default
 * and the toolbar never re-wraps (owner's call, 2026-09-24). */
export function MetalKindSelect({ value, onChange }: MetalKindSelectProps) {
  const { t } = useTranslation();
  return (
    <Select
      aria-label={t('catalog.metalKind')}
      active={value != null}
      triggerLabel={
        <span className={styles.label}>
          <span className={styles.labelGhost} aria-hidden="true">
            {t('catalog.metalKind')}
          </span>
          <span>
            {value === 'precious'
              ? t('catalog.metalPrecious')
              : value === 'base'
                ? t('catalog.metalBase')
                : t('catalog.metalKind')}
          </span>
        </span>
      }
      value={value ?? ''}
      onChange={(event) => onChange((event.target.value as MetalKind) || null)}
    >
      <option value="">{t('catalog.all')}</option>
      <option value="precious">{t('catalog.metalPrecious')}</option>
      <option value="base">{t('catalog.metalBase')}</option>
    </Select>
  );
}
