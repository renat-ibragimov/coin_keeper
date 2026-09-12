import { Check } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import styles from './Select.module.css';

export interface MultiSelectOption {
  value: string;
  label: ReactNode;
  searchText?: string;
}

interface MultiSelectProps {
  label?: ReactNode;
  /** Shown on the trigger when nothing is picked, e.g. "Усі країни". */
  placeholder: ReactNode;
  options: MultiSelectOption[];
  value: string[];
  onChange: (value: string[]) => void;
  disabled?: boolean;
  id?: string;
  'aria-label'?: string;
  searchable?: boolean;
  searchPlaceholder?: string;
  /** Centers the field label over the control (catalog/collection filter toolbars). */
  centerLabel?: boolean;
}

/** Same look and keyboard model as `Select`, but toggling an option leaves
 *  the menu open and a checkbox marks each one — several countries, series,
 *  denominations, types or materials can be on at once (docs/08-ui-map.md,
 *  catalog/collection filters, 2026-09-12). An empty `value` means "every
 *  option", same as `Select`'s own leading "Усі" item — there is no
 *  separate all-of-them row to select. */
export function MultiSelect({
  label,
  placeholder,
  options,
  value,
  onChange,
  disabled,
  id,
  searchable,
  searchPlaceholder,
  centerLabel,
  ...rest
}: MultiSelectProps) {
  const { t } = useTranslation();
  const autoId = useId();
  const baseId = id ?? autoId;
  const labelId = `${baseId}-label`;
  const listboxId = `${baseId}-listbox`;

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);

  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listboxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const filtered = useMemo(() => {
    const indexed = options.map((option, index) => ({ option, index }));
    if (!searchable || !query.trim()) return indexed;
    const needle = query.trim().toLocaleLowerCase();
    return indexed.filter(({ option }) =>
      (option.searchText ?? textOf(option.label)).toLocaleLowerCase().includes(needle),
    );
  }, [options, searchable, query]);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActiveIndex(0);
    if (searchable) searchInputRef.current?.focus();
    else listboxRef.current?.focus();
  }, [open, searchable]);

  useEffect(() => {
    if (!open) return;
    setActiveIndex((current) => Math.min(current, Math.max(filtered.length - 1, 0)));
  }, [filtered.length, open]);

  const optionDomId = (index: number) => `${baseId}-option-${index}`;

  const toggle = (optionValue: string) => {
    if (value.includes(optionValue)) onChange(value.filter((v) => v !== optionValue));
    else onChange([...value, optionValue]);
  };

  const moveActive = (delta: number) => {
    if (filtered.length === 0) return;
    setActiveIndex((current) => {
      let next = current + delta;
      if (next < 0) next = filtered.length - 1;
      if (next >= filtered.length) next = 0;
      return next;
    });
  };

  const handleListKeyDown = (event: KeyboardEvent) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        moveActive(1);
        break;
      case 'ArrowUp':
        event.preventDefault();
        moveActive(-1);
        break;
      case 'Home':
        event.preventDefault();
        setActiveIndex(0);
        break;
      case 'End':
        event.preventDefault();
        setActiveIndex(filtered.length - 1);
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        if (filtered[activeIndex]) toggle(filtered[activeIndex].option.value);
        break;
      case 'Escape':
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
        break;
      case 'Tab':
        setOpen(false);
        break;
      default:
        break;
    }
  };

  const active = filtered[activeIndex];
  const selectedOptions = options.filter((option) => value.includes(option.value));
  const triggerText =
    selectedOptions.length === 0
      ? placeholder
      : selectedOptions.length === 1
        ? selectedOptions[0]!.label
        : t('common.selectedCount', { count: selectedOptions.length });

  return (
    <div className={styles.wrapper} ref={rootRef}>
      {label ? (
        <span
          className={[styles.label, centerLabel ? styles.labelCenter : '']
            .filter(Boolean)
            .join(' ')}
          id={labelId}
        >
          {label}
        </span>
      ) : null}
      <div className={styles.control}>
        <button
          {...rest}
          type="button"
          ref={triggerRef}
          id={baseId}
          className={[styles.trigger, open ? styles.triggerOpen : ''].filter(Boolean).join(' ')}
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-labelledby={label ? labelId : undefined}
          onClick={() => setOpen((current) => !current)}
        >
          <span className={styles.triggerText}>{triggerText}</span>
          <span className={styles.arrow} aria-hidden="true" />
        </button>

        {open ? (
          <div className={styles.menu}>
            {searchable ? (
              <div className={styles.searchRow}>
                <span className={styles.searchIcon} aria-hidden="true" />
                <input
                  ref={searchInputRef}
                  type="text"
                  className={styles.searchInput}
                  placeholder={searchPlaceholder}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={handleListKeyDown}
                  aria-label={searchPlaceholder}
                  aria-controls={listboxId}
                  aria-activedescendant={active ? optionDomId(active.index) : undefined}
                  aria-autocomplete="list"
                />
              </div>
            ) : null}
            {selectedOptions.length > 0 ? (
              <div
                className={styles.clearRow}
                role="button"
                tabIndex={0}
                onClick={() => onChange([])}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onChange([]);
                  }
                }}
              >
                {placeholder}
              </div>
            ) : null}
            <div
              ref={listboxRef}
              id={listboxId}
              role="listbox"
              aria-multiselectable="true"
              aria-labelledby={label ? labelId : undefined}
              tabIndex={-1}
              className={styles.list}
              onKeyDown={searchable ? undefined : handleListKeyDown}
              aria-activedescendant={!searchable && active ? optionDomId(active.index) : undefined}
            >
              {filtered.map(({ option, index }, position) => {
                const checked = value.includes(option.value);
                return (
                  <div
                    key={option.value}
                    id={optionDomId(index)}
                    role="option"
                    aria-selected={checked}
                    className={[styles.option, position === activeIndex ? styles.optionActive : '']
                      .filter(Boolean)
                      .join(' ')}
                    onMouseEnter={() => setActiveIndex(position)}
                    onClick={() => toggle(option.value)}
                  >
                    <span className={styles.optionText}>{option.label}</span>
                    <span
                      className={[styles.checkbox, checked ? styles.checkboxChecked : '']
                        .filter(Boolean)
                        .join(' ')}
                      aria-hidden="true"
                    >
                      {checked ? <Check strokeWidth={3} /> : null}
                    </span>
                  </div>
                );
              })}
              {filtered.length === 0 ? <div className={styles.empty}>—</div> : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function textOf(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  return '';
}
