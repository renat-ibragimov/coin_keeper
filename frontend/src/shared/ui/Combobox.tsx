import { Check, ChevronDown } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { InputHTMLAttributes, KeyboardEvent } from 'react';

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
  id,
  className,
  disabled,
  onFocus,
  onBlur,
  ...rest
}: ComboboxProps) {
  const autoId = useId();
  const baseId = id ?? autoId;
  const listboxId = `${baseId}-listbox`;

  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const needle = value.trim();
    if (!needle) return options;
    return options.filter((option) => option.startsWith(needle));
  }, [options, value]);

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
    setOpen(false);
    // The input never actually lost focus (a plain, non-focusable option div
    // doesn't steal it), so re-focusing here would just re-trigger onFocus
    // and reopen the dropdown it was supposed to close.
  };

  const optionDomId = (index: number) => `${baseId}-option-${index}`;

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (!open) {
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
    <div className={comboStyles.wrapper} ref={rootRef}>
      <input
        {...rest}
        ref={inputRef}
        id={baseId}
        type="text"
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
              </div>
            ))}
            {filtered.length === 0 ? <div className={selectStyles.empty}>—</div> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
