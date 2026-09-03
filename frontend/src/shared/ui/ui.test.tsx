import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { Badge } from './Badge';
import { Button } from './Button';
import { pageItems } from './pageItems';
import { Pagination } from './Pagination';
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
