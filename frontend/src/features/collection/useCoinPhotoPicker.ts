import { useRef, useState } from 'react';
import type { ChangeEvent } from 'react';

import type { CoinSide } from './SelectedCoin';

/**
 * The file-input-then-crop dance shared by every place a coin photo is
 * picked: the "Додати" page (buffers the blob locally) and the edit page
 * (uploads it right away) differ only in what happens once a square comes
 * back, which is why this hook stops at `onPicked` and hands the rest to
 * the caller.
 */
export function useCoinPhotoPicker(onPicked: (side: CoinSide, blob: Blob) => void) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [side, setSide] = useState<CoinSide | null>(null);
  const [raw, setRaw] = useState<string | null>(null);

  function releaseRaw() {
    setRaw((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
  }

  function pick(nextSide: CoinSide) {
    setSide(nextSide);
    fileInput.current?.click();
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Clearing the input is what lets the same file be picked twice.
    event.target.value = '';
    if (!file) return;
    releaseRaw();
    setRaw(URL.createObjectURL(file));
  }

  function onCropSave(blob: Blob) {
    if (side) onPicked(side, blob);
    releaseRaw();
  }

  return { fileInput, raw, pick, onFileChange, onCropSave, cancel: releaseRaw };
}
