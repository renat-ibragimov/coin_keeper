import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { MultiSelect } from './MultiSelect';

const OPTIONS = [
  { value: '1', label: 'Україна' },
  { value: '2', label: 'США' },
  { value: '3', label: 'Польща' },
];

function Controlled({ onChange }: { onChange: (value: string[]) => void }) {
  const [value, setValue] = useState<string[]>([]);
  return (
    <MultiSelect
      aria-label="Країна"
      placeholder="Усі країни"
      options={OPTIONS}
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

describe('MultiSelect', () => {
  it('shows the placeholder when nothing is picked', () => {
    render(<Controlled onChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Країна' })).toHaveTextContent('Усі країни');
  });

  it('adds and removes options without closing the menu', () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Країна' }));

    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));
    expect(onChange).toHaveBeenLastCalledWith(['1']);
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('option', { name: 'США' }));
    expect(onChange).toHaveBeenLastCalledWith(['1', '2']);

    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));
    expect(onChange).toHaveBeenLastCalledWith(['2']);
  });

  it('shows one label directly, and a count once more than one is picked', () => {
    render(<Controlled onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Країна' }));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));
    expect(screen.getByRole('button', { name: 'Країна' })).toHaveTextContent('Україна');

    fireEvent.click(screen.getByRole('option', { name: 'США' }));
    expect(screen.getByRole('button', { name: 'Країна' })).toHaveTextContent('Обрано: 2');
  });

  it('clears every selection from the "all" row', () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Країна' }));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));
    fireEvent.click(screen.getByRole('option', { name: 'США' }));

    fireEvent.click(screen.getByText('Усі країни'));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it('closes on Escape', () => {
    render(<Controlled onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Країна' }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});
