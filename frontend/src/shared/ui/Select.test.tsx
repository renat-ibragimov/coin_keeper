import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { Select } from './Select';

function Grouped({ onChange }: { onChange: (value: string) => void }) {
  const [value, setValue] = useState('');
  return (
    <Select
      label="Рік"
      value={value}
      onChange={(event) => {
        setValue(event.target.value);
        onChange(event.target.value);
      }}
    >
      <option value="">—</option>
      <optgroup label="2020-ті">
        <option value="2021">2021</option>
        <option value="2020">2020</option>
      </optgroup>
      <optgroup label="2010-ті">
        <option value="2015">2015</option>
      </optgroup>
    </Select>
  );
}

describe('Select optgroup support', () => {
  it('renders a heading before each group of options, in source order', () => {
    render(<Grouped onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button'));

    const listbox = screen.getByRole('listbox');
    const rows = Array.from(listbox.children).map((el) => el.textContent);
    expect(rows).toEqual(['—', '2020-ті', '2021', '2020', '2010-ті', '2015']);
  });

  it('still selects a grouped option and reflects it on the trigger', () => {
    const onChange = vi.fn();
    render(<Grouped onChange={onChange} />);
    fireEvent.click(screen.getByRole('button'));
    fireEvent.click(screen.getByRole('option', { name: '2015' }));

    expect(onChange).toHaveBeenCalledWith('2015');
    expect(screen.getByRole('button')).toHaveTextContent('2015');
  });
});
