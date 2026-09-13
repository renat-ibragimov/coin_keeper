import { Check, ChevronDown, Plus, Trash2 } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { InputHTMLAttributes, KeyboardEvent, ReactNode } from 'react';

import comboStyles from './Combobox.module.css';
import inputStyles from './Input.module.css';
import selectStyles from './Select.module.css';

interface ComboboxProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'onChange' | 'value' | 'list'
> {
  value: string;
  onChange: (event: { target: { value: string } }) => void;
  /** Suggestions shown below the field — a hint, never a constraint: any text can still be typed and committed. */
  options: string[];
  /** A visible label above the field, same slot as Input's — the year
   *  filters skip this and use their own group title plus aria-label instead. */
  label?: ReactNode;
  hint?: ReactNode;
  /** Which options may be deleted from the list itself (a preset, say,
   *  never should). Omit alongside onDeleteOption to skip this affordance
   *  entirely -- the year filters and most other callers do. */
  isOptionDeletable?: (option: string) => boolean;
  onDeleteOption?: (option: string) => void;
  deleteOptionLabel?: string;
  /** A pinned row at the top of the menu, shown only while browsing (an
   *  empty field, or one that still holds the value it was opened with):
   *  clicking it clears the field and refocuses it, ready to type a new
   *  entry. Without this, "erase what's there and type over it" is not a
   *  thing most people would guess (owner's report, 2026-09-13). */
  addNewLabel?: ReactNode;
  /** Shown once the owner has typed something that isn't already a known
   *  option -- spells out that Enter is what commits it, since a filtered
   *  list on its own doesn't say that. */
  createHint?: (typedValue: string) => ReactNode;
  /** Fires when a value is explicitly finalized -- picking an existing
   *  option, or pressing Enter on freshly typed text -- as opposed to
   *  onChange, which also fires on every keystroke while still typing. */
  onCommitValue?: (value: string) => void;
}

/**
 * A themed `<input>` with a dropdown of suggestions attached — the field the
 * year filters use (docs/08-ui-map.md): typing is always free, the list
 * beneath it (styled like `Select`'s own menu) is just a faster way to pick
 * a common value. Unlike `Select`, there is no "selected option": the
 * field's value is whatever text is in it, matched against the list or not.
 */
export function Combobox({
  value,
  onChange,
  options,
  label,
  hint,
  id,
  className,
  disabled,
  onFocus,
  onBlur,
  isOptionDeletable,
  onDeleteOption,
  deleteOptionLabel,
  addNewLabel,
  createHint,
  onCommitValue,
  ...rest
}: ComboboxProps) {
  const autoId = useId();
  const baseId = id ?? autoId;
  const listboxId = `${baseId}-listbox`;

  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  // The value the field held the moment the dropdown was (re)opened: until
  // the owner actually types something new, the list shows everything
  // rather than just what happens to prefix-match an already-picked value
  // (docs/08-ui-map.md) -- otherwise reopening a field that already holds
  // "В дорозі" hides every other option, "Вдома" included, which reads as
  // "the other locations vanished" rather than "this is just a filter".
  // State, not a ref: filtered below must actually recompute when this
  // changes, and a ref mutation alone doesn't trigger that.
  const [openedWithValue, setOpenedWithValue] = useState(value);

  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const needle = value.trim();
    if (!needle || value === openedWithValue) return options;
    return options.filter((option) => option.startsWith(needle));
  }, [options, value, openedWithValue]);
  // Same array reference only on the "show everything" branch above --
  // a cheap, reliable way to tell "browsing" from "typing something new"
  // without duplicating that condition.
  const isBrowsing = filtered === options;
  const trimmed = value.trim();
  const isNewValue = trimmed !== '' && !options.includes(trimmed);

  useEffect(() => {
    setActiveIndex(-1);
  }, [filtered]);

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

  const commit = (option: string) => {
    onChange({ target: { value: option } });
    onCommitValue?.(option);
    setOpen(false);
    // The input never actually lost focus (a plain, non-focusable option div
    // doesn't steal it), so re-focusing here would just re-trigger onFocus
    // and reopen the dropdown it was supposed to close.
  };

  const startNewEntry = () => {
    onChange({ target: { value: '' } });
    setOpenedWithValue('');
    inputRef.current?.focus();
  };

  const optionDomId = (index: number) => `${baseId}-option-${index}`;

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (!open) {
          setOpenedWithValue(value);
          setOpen(true);
          return;
        }
        setActiveIndex((current) => Math.min(current + 1, filtered.length - 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setActiveIndex((current) => Math.max(current - 1, 0));
        break;
      case 'Enter':
        if (open && activeIndex >= 0 && filtered[activeIndex]) {
          event.preventDefault();
          commit(filtered[activeIndex]);
        } else if (isNewValue) {
          event.preventDefault();
          onCommitValue?.(trimmed);
          setOpen(false);
        } else {
          setOpen(false);
        }
        break;
      case 'Tab':
        setOpen(false);
        break;
      default:
        break;
    }
  };

  return (
    <div className={inputStyles.wrapper}>
      {label ? (
        <label className={inputStyles.label} htmlFor={baseId}>
          {label}
        </label>
      ) : null}
      <div className={comboStyles.wrapper} ref={rootRef}>
        <input
          {...rest}
          ref={inputRef}
          id={baseId}
          type="text"
          // The field's own suggestion list already is the autocomplete;
          // the browser's native one only adds unrelated text it remembers
          // from other sites' forms sharing no real relation to this field
          // (docs/08-ui-map.md).
          autoComplete="off"
          value={value}
          disabled={disabled}
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={open && activeIndex >= 0 ? optionDomId(activeIndex) : undefined}
          className={[inputStyles.input, comboStyles.input, className ?? '']
            .filter(Boolean)
            .join(' ')}
          onChange={(event) => {
            onChange(event);
            setOpen(true);
          }}
          onFocus={(event) => {
            setOpenedWithValue(value);
            setOpen(true);
            onFocus?.(event);
          }}
          onBlur={onBlur}
          onKeyDown={handleKeyDown}
        />
        <button
          type="button"
          tabIndex={-1}
          disabled={disabled}
          aria-hidden="true"
          className={[comboStyles.chevron, open ? comboStyles.chevronOpen : '']
            .filter(Boolean)
            .join(' ')}
          onClick={() => {
            if (open) {
              setOpen(false);
            } else {
              setOpenedWithValue(value);
              setOpen(true);
              inputRef.current?.focus();
            }
          }}
        >
          <ChevronDown strokeWidth={2} />
        </button>

        {open && !disabled ? (
          <div className={selectStyles.menu}>
            <div id={listboxId} role="listbox" className={selectStyles.list}>
              {addNewLabel && isBrowsing ? (
                <div
                  role="option"
                  aria-selected={false}
                  className={[selectStyles.option, comboStyles.addNew].join(' ')}
                  // Keeps focus on the input through the click, same as the
                  // per-option delete button above.
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={startNewEntry}
                >
                  <span className={comboStyles.addNewLabel}>
                    <Plus size={14} aria-hidden="true" />
                    <span className={selectStyles.optionText}>{addNewLabel}</span>
                  </span>
                </div>
              ) : null}
              {filtered.map((option, index) => (
                <div
                  key={option}
                  id={optionDomId(index)}
                  role="option"
                  aria-selected={option === value}
                  className={[
                    selectStyles.option,
                    index === activeIndex ? selectStyles.optionActive : '',
                    option === value ? selectStyles.optionSelected : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => commit(option)}
                >
                  <span className={selectStyles.optionText}>{option}</span>
                  {option === value ? (
                    <span className={selectStyles.check} aria-hidden="true">
                      <Check strokeWidth={2.25} />
                    </span>
                  ) : null}
                  {onDeleteOption && isOptionDeletable?.(option) ? (
                    <button
                      type="button"
                      className={comboStyles.optionDelete}
                      aria-label={deleteOptionLabel}
                      // Keeps focus on the input instead of the button, so the
                      // click doesn't blur-close the menu before it registers.
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDeleteOption(option);
                      }}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  ) : null}
                </div>
              ))}
              {filtered.length === 0 && !(createHint && isNewValue) ? (
                <div className={selectStyles.empty}>—</div>
              ) : null}
            </div>
            {createHint && isNewValue ? (
              <div className={comboStyles.createHint}>{createHint(trimmed)}</div>
            ) : null}
          </div>
        ) : null}
      </div>
      {hint ? <div className={inputStyles.hint}>{hint}</div> : null}
    </div>
  );
}
