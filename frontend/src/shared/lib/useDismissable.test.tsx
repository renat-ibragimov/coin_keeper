import { fireEvent, render, screen } from '@testing-library/react';
import { useRef, useState } from 'react';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { useDismissable } from './useDismissable';

function Popup() {
  const [open, setOpen] = useState(true);
  const panel = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  useDismissable(open, () => setOpen(false), { inside: [panel, toggle] });
  return (
    <div>
      <button ref={toggle} onClick={() => setOpen((value) => !value)}>
        toggle
      </button>
      <button onClick={() => navigate('/elsewhere')}>go</button>
      <p>outside</p>
      {open ? (
        <div ref={panel} data-testid="panel">
          <button>inside</button>
        </div>
      ) : null}
    </div>
  );
}

function renderPopup() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="*" element={<Popup />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('useDismissable', () => {
  it('closes on Escape', () => {
    renderPopup();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('panel')).toBeNull();
  });

  it('closes on a press outside but not inside or on the toggle', () => {
    renderPopup();
    fireEvent.pointerDown(screen.getByText('inside'));
    expect(screen.getByTestId('panel')).toBeInTheDocument();
    fireEvent.pointerDown(screen.getByText('toggle'));
    expect(screen.getByTestId('panel')).toBeInTheDocument();
    fireEvent.pointerDown(screen.getByText('outside'));
    expect(screen.queryByTestId('panel')).toBeNull();
  });

  it('closes when the route changes', () => {
    renderPopup();
    fireEvent.click(screen.getByText('go'));
    expect(screen.queryByTestId('panel')).toBeNull();
  });

  it('stays open while nothing happens and reopens cleanly', () => {
    renderPopup();
    expect(screen.getByTestId('panel')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(screen.getByText('toggle'));
    expect(screen.getByTestId('panel')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Enter' });
    expect(screen.getByTestId('panel')).toBeInTheDocument();
  });
});
