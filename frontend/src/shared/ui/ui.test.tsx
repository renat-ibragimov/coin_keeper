import { readFile } from 'node:fs/promises';
import path from 'node:path';

import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { Badge } from './Badge';
import { Button } from './Button';
import { CoinImage } from './CoinImage';
import { FiltersShell, FiltersToolbar } from './FiltersShell';
import { Input } from './Input';
import { pageItems } from './pageItems';
import { Pagination } from './Pagination';
import { EmptyState, ErrorState } from './States';
import { Toggle } from './Toggle';

describe('Button', () => {
  it('renders and handles clicks', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('is disabled while loading', () => {
    render(<Button loading>Waiting</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});

describe('Badge', () => {
  it('renders its content', () => {
    render(<Badge tone="success">In collection</Badge>);
    expect(screen.getByText('In collection')).toBeInTheDocument();
  });
});

describe('Toggle', () => {
  it('flips on click', async () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} label="Show archived" />);
    await userEvent.click(screen.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('CoinImage', () => {
  it('draws the placeholder instead of an empty image', () => {
    const { container } = render(<CoinImage src={null} alt="" />);
    expect(screen.getByTestId('coin-placeholder')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
  });

  it('falls back to the placeholder once and does not ask for the file again', () => {
    const { container, rerender } = render(<CoinImage src="https://ucoin.net/a.jpg" alt="" />);
    fireEvent.error(container.querySelector('img')!);
    expect(screen.getByTestId('coin-placeholder')).toBeInTheDocument();

    rerender(<CoinImage src="https://ucoin.net/a.jpg" alt="" />);
    expect(container.querySelector('img')).toBeNull();
  });

  it('gives a different url its own attempt', () => {
    const { container, rerender } = render(<CoinImage src="https://ucoin.net/a.jpg" alt="" />);
    fireEvent.error(container.querySelector('img')!);

    rerender(<CoinImage src="/media/b.jpg" alt="" />);
    expect(container.querySelector('img')).toHaveAttribute('src', '/media/b.jpg');
  });
});

describe('pageItems', () => {
  it('collapses long ranges with gaps', () => {
    expect(pageItems(5, 77)).toEqual([1, 'gap', 4, 5, 6, 'gap', 77]);
  });

  it('keeps short ranges dense', () => {
    expect(pageItems(2, 3)).toEqual([1, 2, 3]);
  });
});

describe('Pagination', () => {
  it('marks the current page and pages around it', () => {
    render(<Pagination page={2} pageCount={5} onChange={() => {}} />);
    expect(screen.getByRole('button', { name: '2' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: '5' })).toBeInTheDocument();
  });

  it('renders nothing for a single page', () => {
    const { container } = render(<Pagination page={1} pageCount={1} onChange={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('FiltersShell', () => {
  it('renders the field slot and hides the chip row when nothing is active', () => {
    render(
      <FiltersShell activeFilters={[]} onReset={() => {}}>
        <div>a field</div>
      </FiltersShell>,
    );
    expect(screen.getByText('a field')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /скинути/i })).toBeNull();
  });

  it('removes a chip and resets from the active-filters row', async () => {
    const onRemove = vi.fn();
    const onReset = vi.fn();
    render(
      <FiltersShell
        activeFilters={[{ key: 'country', label: 'Україна', onRemove }]}
        onReset={onReset}
      >
        <div />
      </FiltersShell>,
    );
    await userEvent.click(screen.getByRole('button', { name: /Україна/ }));
    expect(onRemove).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole('button', { name: /скинути/i }));
    expect(onReset).toHaveBeenCalledOnce();
  });
});

describe('FiltersToolbar', () => {
  it('shows the result count and drives view, sort and order changes', async () => {
    const onViewChange = vi.fn();
    const onSortChange = vi.fn();
    const onOrderChange = vi.fn();
    render(
      <FiltersToolbar<'cards' | 'table'>
        shown={8}
        total={20}
        view="cards"
        viewOptions={[
          { value: 'cards', label: 'Cards' },
          { value: 'table', label: 'Table' },
        ]}
        onViewChange={onViewChange}
        sort="date"
        sortOptions={[
          { value: 'date', label: 'By date' },
          { value: 'title', label: 'By title' },
        ]}
        onSortChange={onSortChange}
        order="desc"
        onOrderChange={onOrderChange}
      />,
    );
    expect(screen.getByText('Показано 8 з 20')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /фільтри/i })).toBeNull();

    await userEvent.click(screen.getByRole('tab', { name: 'Table' }));
    expect(onViewChange).toHaveBeenCalledWith('table');

    await userEvent.click(screen.getByRole('button', { name: /спаданням/i }));
    expect(onOrderChange).toHaveBeenCalledOnce();
  });

  it('shows the mobile filters trigger only when a handler is given', () => {
    render(
      <FiltersToolbar<'cards' | 'table'>
        shown={1}
        total={1}
        view="cards"
        viewOptions={[{ value: 'cards', label: 'Cards' }]}
        onViewChange={() => {}}
        sort="date"
        sortOptions={[{ value: 'date', label: 'By date' }]}
        onSortChange={() => {}}
        order="asc"
        onOrderChange={() => {}}
        onOpenFilters={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: /фільтри/i })).toBeInTheDocument();
  });
});

describe('Input with a trailing control', () => {
  it('anchors the control to the input, not to the hint or error below it', () => {
    render(
      <Input
        label="New password"
        hint="At least 10 characters"
        trailing={<button type="button">reveal</button>}
      />,
    );
    const control = screen.getByTestId('input-control');
    expect(control).toContainElement(screen.getByLabelText('New password'));
    expect(control).toContainElement(screen.getByRole('button', { name: 'reveal' }));
    expect(control).not.toHaveTextContent('At least 10 characters');
    expect(screen.getByText('At least 10 characters')).toBeInTheDocument();
  });

  it('renders no extra wrapper without a trailing control', () => {
    render(<Input label="Email" hint="hint" />);
    expect(screen.queryByTestId('input-control')).toBeNull();
  });
});

describe('EmptyState', () => {
  it('defaults to a lucide icon, not a text glyph', () => {
    const { container } = render(<EmptyState title="Nothing here" />);
    const icon = container.querySelector('svg');
    expect(icon).not.toBeNull();
    expect(container.textContent).not.toMatch(/[◎⚠]/);
  });

  it('renders a custom icon when given one', () => {
    render(<EmptyState title="Nothing here" icon={<span data-testid="custom-icon" />} />);
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });

  it('stays unwrapped by default, for in-content "nothing found" states', () => {
    const { container } = render(<EmptyState title="Nothing here" />);
    expect(container.firstElementChild?.className).not.toMatch(/card/i);
  });

  it('sits on a card surface with variant="card", for whole-page empty states', () => {
    const { container } = render(<EmptyState title="Nothing here" variant="card" />);
    expect(container.firstElementChild?.className).toMatch(/card/i);
  });

  it('gives the card variant a definite width, not a shrink-to-fit one', async () => {
    // Regression guard: as a flex item with auto margins, the card would
    // otherwise size to its own content and end up a different width on
    // every page depending on the text — max-width alone isn't enough.
    // vitest runs with css:false, so this checks the source rule directly
    // rather than a (here-unavailable) computed style.
    const css = await readFile(
      path.resolve(process.cwd(), 'src/shared/ui/States.module.css'),
      'utf-8',
    );
    const rule = css.match(/\.cardVariant\s*{([^}]*)}/)?.[1] ?? '';
    expect(rule).toMatch(/width:\s*100%/);
  });

  it('renders the note below the actions', () => {
    render(<EmptyState title="Nothing here" note={<a href="/import">Import</a>} />);
    expect(screen.getByRole('link', { name: 'Import' })).toHaveAttribute('href', '/import');
  });
});

describe('ErrorState', () => {
  it('defaults to a lucide icon, not a text glyph', () => {
    const { container } = render(<ErrorState />);
    const icon = container.querySelector('svg');
    expect(icon).not.toBeNull();
    expect(container.textContent).not.toMatch(/[◎⚠]/);
  });
});
