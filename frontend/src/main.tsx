// Self-hosted fonts. Each weight file carries every subset with
// unicode-range, Ukrainian glyphs included (checked for U+0490 ґ).
import '@fontsource/playfair-display/400.css';
import '@fontsource/playfair-display/600.css';
import '@fontsource/playfair-display/700.css';
import '@fontsource/source-sans-3/400.css';
import '@fontsource/source-sans-3/600.css';
import '@fontsource/source-sans-3/700.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@/shared/i18n';
import '@/shared/theme/tokens.css';

import { App } from './app/App';

// The browser's own scroll restoration races with App.tsx's ScrollToTop and
// is what made the coin card page land mid-scroll or at the bottom instead
// of the top; App.tsx owns scroll position on every navigation instead.
if ('scrollRestoration' in window.history) {
  window.history.scrollRestoration = 'manual';
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// TEMPORARY — mobile viewport-overflow debugging, remove once diagnosed.
(function mountViewportDebugBadge() {
  const badge = document.createElement('div');
  badge.style.cssText =
    'position:fixed;top:0;right:0;z-index:99999;background:#000;color:#0f0;' +
    'font:10px/1.4 monospace;padding:4px 6px;white-space:pre;pointer-events:none;';
  document.body.appendChild(badge);
  const update = () => {
    const de = document.documentElement;
    const vv = window.visualViewport;
    badge.textContent =
      `iw=${window.innerWidth} ih=${window.innerHeight}\n` +
      `cw=${de.clientWidth} sw=${de.scrollWidth}\n` +
      `vv=${vv ? Math.round(vv.width) : '-'}@${vv ? vv.scale.toFixed(2) : '-'} off=${vv ? Math.round(vv.offsetLeft) : '-'}\n` +
      `dpr=${window.devicePixelRatio}`;
  };
  update();
  window.addEventListener('resize', update);
  window.addEventListener('scroll', update, true);
  window.visualViewport?.addEventListener('resize', update);
  window.visualViewport?.addEventListener('scroll', update);
})();
