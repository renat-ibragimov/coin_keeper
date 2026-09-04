import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { CountryOut } from '@/shared/api/types';
import { useDismissable } from '@/shared/lib/useDismissable';
import { Input } from '@/shared/ui';

import styles from './CountrySelect.module.css';

interface CountrySelectProps {
  countries: CountryOut[];
  value: CountryOut | null;
  onSelect: (country: CountryOut) => void;
  error?: string;
}

const MAX_SUGGESTIONS = 12;

function matches(country: CountryOut, query: string): boolean {
  // All three names plus the code: the reader may know the country under any
  // of them, and a personal item may be of any issuer ever (docs/04, rule 2).
  const haystack = [
    country.name,
    country.nameOriginal,
    country.nameUk,
    country.nameEn,
    country.code,
  ]
    .filter(Boolean)
    .join(' ')
    .toLocaleLowerCase();
  return haystack.includes(query);
}

/** A country field over the full list of issuers, searchable by any name. */
export function CountrySelect({ countries, value, onSelect, error }: CountrySelectProps) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useDismissable(open, () => setOpen(false), { inside: [root], routeChange: false });

  const suggestions = useMemo(() => {
    const query = text.trim().toLocaleLowerCase();
    const pool = query ? countries.filter((country) => matches(country, query)) : countries;
    return pool.slice(0, MAX_SUGGESTIONS);
  }, [countries, text]);

  const choose = (country: CountryOut) => {
    onSelect(country);
    setText('');
    setOpen(false);
  };

  return (
    <div className={styles.select} ref={root}>
      <Input
        type="search"
        label={t('catalog.country')}
        required
        placeholder={value ? value.name : t('createItem.pickCountry')}
        hint={
          value ? t('createItem.countryChosen', { name: value.name }) : t('createItem.countryHint')
        }
        error={error}
        value={text}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
        }}
        role="combobox"
        aria-expanded={open}
        aria-controls="country-select-options"
      />
      {open && suggestions.length > 0 ? (
        <ul id="country-select-options" className={styles.options} role="listbox">
          {suggestions.map((country) => (
            <li key={country.id}>
              <button
                type="button"
                role="option"
                aria-selected={country.id === value?.id}
                className={styles.option}
                onClick={() => choose(country)}
              >
                <span className={styles.name}>{country.name}</span>
                {country.nameOriginal !== country.name ? (
                  <span className={styles.original}>{country.nameOriginal}</span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
