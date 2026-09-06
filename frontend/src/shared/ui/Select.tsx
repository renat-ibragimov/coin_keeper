import { Children, isValidElement, useEffect, useId, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent, OptionHTMLAttributes, ReactNode } from 'react';

import styles from './Select.module.css';

interface SelectOption {
  value: string;
  disabled: boolean;
  content: ReactNode;
  searchText: string;
}

interface SelectProps {
  label?: ReactNode;
  error?: ReactNode;
  hint?: ReactNode;
  id?: string;
  className?: string;
  value: string | number;
  onChange: (event: { target: { value: string } }) => void;
  disabled?: boolean;
  'aria-label'?: string;
  /** Adds a text filter at the top of the menu, for lists too long to scan (docs/08-ui-map.md: series). */
  searchable?: boolean;
  searchPlaceholder?: string;
  /** Centers the field label over the control, for a toolbar of narrow columns (catalog filters). */
  centerLabel?: boolean;
  children: ReactNode;
}

function textOf(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  return '';
}

function parseOptions(children: ReactNode): SelectOption[] {
  return Children.toArray(children).flatMap((child) => {
    if (!isValidElement<OptionHTMLAttributes<HTMLOptionElement>>(child) || child.type !== 'option')
      return [];
    const content = child.props.children;
    return [
      {
        value: String(child.props.value ?? ''),
        disabled: Boolean(child.props.disabled),
        content,
        searchText: textOf(content).toLocaleLowerCase(),
      },
    ];
  });
}

/** A themed replacement for the native <select>: same open-menu-of-<option>s
 *  API, but the menu is our own listbox so it never shows the browser's
 *  system highlight colour (docs/08-ui-map.md, catalog toolbar). */
export function Select({
  label,
  error,
  hint,
  id,
  className,
  value,
  onChange,
  disabled,
  searchable,
  searchPlaceholder,
  centerLabel,
  children,
  ...rest
}: SelectProps) {
  const autoId = useId();
  const baseId = id ?? autoId;
  const labelId = `${baseId}-label`;
  const listboxId = `${baseId}-listbox`;

  const options = useMemo(() => parseOptions(children), [children]);
  const stringValue = String(value ?? '');
  const selectedIndex = options.findIndex((option) => option.value === stringValue);

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);

  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listboxRef = useRef<HTMLDivElement>(null);

  // A shared primitive used well outside any router context (e.g. plain
  // forms), so outside-click and Escape are handled locally rather than via
  // useDismissable, which also dismisses on route change.
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
    return indexed.filter(({ option }) => option.searchText.includes(needle));
  }, [options, searchable, query]);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    const startAt = filtered.findIndex(({ index }) => index === selectedIndex);
    setActiveIndex(startAt >= 0 ? startAt : 0);
    if (searchable) {
      searchInputRef.current?.focus();
    } else {
      listboxRef.current?.focus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run when opening
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setActiveIndex((current) => Math.min(current, Math.max(filtered.length - 1, 0)));
  }, [filtered.length, open]);

  const optionDomId = (index: number) => `${baseId}-option-${index}`;

  const select = (option: SelectOption) => {
    if (option.disabled) return;
    onChange({ target: { value: option.value } });
    setOpen(false);
    triggerRef.current?.focus();
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
        if (filtered[activeIndex]) select(filtered[activeIndex].option);
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

  const handleTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter') {
      event.preventDefault();
      setOpen(true);
    }
  };

  const active = filtered[activeIndex];
  const selected = options[selectedIndex];

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
          className={[
            styles.trigger,
            error ? styles.invalid : '',
            open ? styles.triggerOpen : '',
            className ?? '',
          ]
            .filter(Boolean)
            .join(' ')}
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-labelledby={label ? labelId : undefined}
          aria-invalid={error ? true : undefined}
          onClick={() => setOpen((current) => !current)}
          onKeyDown={handleTriggerKeyDown}
        >
          <span className={styles.triggerText}>{selected ? selected.content : ''}</span>
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
            <div
              ref={listboxRef}
              id={listboxId}
              role="listbox"
              aria-labelledby={label ? labelId : undefined}
              tabIndex={-1}
              className={styles.list}
              onKeyDown={searchable ? undefined : handleListKeyDown}
              aria-activedescendant={!searchable && active ? optionDomId(active.index) : undefined}
            >
              {filtered.map(({ option, index }, position) => (
                <div
                  key={option.value}
                  id={optionDomId(index)}
                  role="option"
                  aria-selected={index === selectedIndex}
                  aria-disabled={option.disabled || undefined}
                  className={[
                    styles.option,
                    index === selectedIndex ? styles.optionSelected : '',
                    position === activeIndex ? styles.optionActive : '',
                    option.disabled ? styles.optionDisabled : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onMouseEnter={() => setActiveIndex(position)}
                  onClick={() => select(option)}
                >
                  <span className={styles.optionText}>{option.content}</span>
                  {index === selectedIndex ? (
                    <span className={styles.check} aria-hidden="true">
                      ✓
                    </span>
                  ) : null}
                </div>
              ))}
              {filtered.length === 0 ? <div className={styles.empty}>—</div> : null}
            </div>
          </div>
        ) : null}
      </div>
      {error ? <div className={styles.error}>{error}</div> : null}
      {!error && hint ? <div className={styles.hint}>{hint}</div> : null}
    </div>
  );
}
