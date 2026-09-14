import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { CropDialog } from './CropDialog';
import type { CropDialogProps } from './CropDialog';

const FIXED_AREA = { x: 1, y: 2, width: 100, height: 100 };

// Modal dismisses itself on route change, so it needs a router in scope even
// though these tests never navigate.
function renderDialog(props: CropDialogProps) {
  return render(
    <MemoryRouter>
      <CropDialog {...props} />
    </MemoryRouter>,
  );
}

function MockCropper(props: {
  minZoom: number;
  maxZoom: number;
  rotation: number;
  onCropComplete: (percentages: unknown, pixels: unknown) => void;
}) {
  useEffect(() => {
    props.onCropComplete({}, FIXED_AREA);
    // Runs once per mount, mirroring the real Cropper's first measurement.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div
      data-testid="mock-cropper"
      data-min-zoom={props.minZoom}
      data-max-zoom={props.maxZoom}
      data-rotation={props.rotation}
    />
  );
}

vi.mock('react-easy-crop', () => ({ default: MockCropper }));

function baseProps() {
  return {
    image: 'blob:fake',
    title: 'Crop',
    hint: 'hint',
    zoomLabel: 'Zoom',
    invalidMessage: 'invalid',
    busy: false,
    onCancel: vi.fn(),
    onSave: vi.fn(),
    toBlob: vi.fn(async () => new Blob(['x'], { type: 'image/webp' })),
  };
}

describe('CropDialog', () => {
  it('defaults to the original zoom range and shows no rotation control (avatar behaviour)', () => {
    renderDialog(baseProps());
    const cropper = screen.getByTestId('mock-cropper');
    expect(cropper.dataset.minZoom).toBe('1');
    expect(cropper.dataset.maxZoom).toBe('3');
    expect(screen.queryByLabelText(/rotation/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole('slider')).toHaveLength(1);
  });

  it('accepts a configurable zoom range', () => {
    renderDialog({ ...baseProps(), minZoom: 1, maxZoom: 5 });
    const cropper = screen.getByTestId('mock-cropper');
    expect(cropper.dataset.maxZoom).toBe('5');
    const zoomSlider = screen.getAllByRole('slider')[0] as HTMLInputElement;
    expect(zoomSlider.max).toBe('5');
  });

  it('renders a rotation slider only when enabled, with a working reset', async () => {
    const user = userEvent.setup();
    renderDialog({
      ...baseProps(),
      rotation: { min: -15, max: 15, step: 1, label: 'Rotation', resetLabel: 'Reset rotation' },
    });
    const rotationSlider = screen.getByRole('slider', { name: 'Rotation' }) as HTMLInputElement;
    expect(rotationSlider.min).toBe('-15');
    expect(rotationSlider.max).toBe('15');
    expect(screen.getByText('0°')).toBeInTheDocument();

    const resetButton = screen.getByRole('button', { name: 'Reset rotation' });
    expect(resetButton).toBeDisabled();

    fireEvent.change(rotationSlider, { target: { value: '7' } });
    expect(screen.getByTestId('mock-cropper').dataset.rotation).toBe('7');
    expect(screen.getByText('+7°')).toBeInTheDocument();
    expect(resetButton).not.toBeDisabled();

    await user.click(resetButton);
    expect(screen.getByText('0°')).toBeInTheDocument();
    expect(resetButton).toBeDisabled();
  });

  it('saves with the rotation value once the user picks a save-worthy photo', async () => {
    const user = userEvent.setup();
    const props = baseProps();
    renderDialog(props);

    await user.click(screen.getByRole('button', { name: 'Зберегти' }));
    expect(props.toBlob).toHaveBeenCalledWith('blob:fake', FIXED_AREA, 0);
    expect(props.onSave).toHaveBeenCalledTimes(1);
  });

  it('shows a soft blur warning without blocking "save anyway", and never re-encodes', async () => {
    const user = userEvent.setup();
    const props = baseProps();
    const check = vi.fn(async () => true);
    renderDialog({
      ...props,
      blur: { check, warning: 'Might be blurry', saveAnywayLabel: 'Save anyway' },
    });

    await user.click(screen.getByRole('button', { name: 'Зберегти' }));
    expect(await screen.findByText('Might be blurry')).toBeInTheDocument();
    expect(props.onSave).not.toHaveBeenCalled();
    expect(props.toBlob).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: 'Save anyway' }));
    expect(props.onSave).toHaveBeenCalledTimes(1);
    expect(props.toBlob).toHaveBeenCalledTimes(1);
  });

  it('dismissing the blur warning returns to editing without closing the dialog', async () => {
    const user = userEvent.setup();
    const props = baseProps();
    const check = vi.fn(async () => true);
    renderDialog({
      ...props,
      blur: { check, warning: 'Might be blurry', saveAnywayLabel: 'Save anyway' },
    });

    await user.click(screen.getByRole('button', { name: 'Зберегти' }));
    await screen.findByText('Might be blurry');

    await user.click(screen.getByRole('button', { name: 'Скасувати' }));
    expect(screen.queryByText('Might be blurry')).not.toBeInTheDocument();
    expect(props.onCancel).not.toHaveBeenCalled();
    expect(props.onSave).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Зберегти' })).toBeInTheDocument();
  });

  it('never runs the blur check when the caller opts out (avatar behaviour)', async () => {
    const user = userEvent.setup();
    const props = baseProps();
    renderDialog(props);
    await user.click(screen.getByRole('button', { name: 'Зберегти' }));
    expect(props.onSave).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert', { name: '' })).not.toBeInTheDocument();
  });
});
