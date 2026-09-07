import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { Combobox } from './Combobox';

function Controlled({ onChange }: { onChange: (value: string) => void }) {
  const [value, setValue] = useState('');
  return (
    <Combobox
      aria-label="Рік"
      value={value}
      options={['2021', '2022', '2023']}
      onChange={(event) => {
        setValue(event.target.value);
        onChange(event.target.value);
      }}
    />
  );
}

describe('Combobox', () => {
  it('keeps the dropdown closed until the field is focused or clicked', () => {
    render(<Controlled onChange={vi.fn()} />);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('shows every suggestion on focus', () => {
    render(<Controlled onChange={vi.fn()} />);
    fireEvent.focus(screen.getByLabelText('Рік'));
    expect(screen.getAllByRole('option').map((el) => el.textContent)).toEqual([
      '2021',
      '2022',
      '2023',
    ]);
  });

  it('narrows the suggestions to what was typed, but still accepts free text', () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    const input = screen.getByLabelText('Рік');
    fireEvent.change(input, { target: { value: '202' } });
    expect(onChange).toHaveBeenLastCalledWith('202');
    expect(screen.getAllByRole('option')).toHaveLength(3);

    fireEvent.change(input, { target: { value: '2022' } });
    expect(screen.getAllByRole('option')).toHaveLength(1);

    fireEvent.change(input, { target: { value: '1970' } });
    expect(onChange).toHaveBeenLastCalledWith('1970');
    expect(input).toHaveValue('1970');
  });

  it('fills the field and closes the dropdown when a suggestion is picked', () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    fireEvent.focus(screen.getByLabelText('Рік'));
    fireEvent.click(screen.getByRole('option', { name: '2022' }));

    expect(onChange).toHaveBeenCalledWith('2022');
    expect(screen.getByLabelText('Рік')).toHaveValue('2022');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('closes on Escape without changing the value', () => {
    render(<Controlled onChange={vi.fn()} />);
    const input = screen.getByLabelText('Рік');
    fireEvent.focus(input);
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});
