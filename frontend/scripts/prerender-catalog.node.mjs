import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

import { prerenderCatalog } from './prerender-catalog.mjs';

const template =
  '<html><head><title>Bakost Numismatics</title><meta name="description" content="old" /><meta property="og:title" content="old" /><meta property="og:description" content="old" /><meta property="og:type" content="website" /><meta property="og:image" content="old" /></head><body><div id="root"></div></body></html>';

test('prerenders public coin metadata, content and sitemap without prices', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'bakost-seo-'));
  await writeFile(join(dir, 'index.html'), template);
  const calls = [];
  const count = await prerenderCatalog({
    siteUrl: 'https://example.test',
    distDir: dir,
    fetchImpl: async (url) => {
      calls.push(url);
      return {
        ok: true,
        json: async () => ({
          total: 1,
          items: [
            {
              id: 17,
              title: 'Монета <Ріка>',
              country: 'Україна',
              year: 2020,
              denomination: { label: '5 гривень' },
              seriesName: 'Природа',
              marketPriceUah: '9999.00',
              priceSource: 'private-source',
            },
          ],
        }),
      };
    },
  });
  assert.equal(count, 1);
  assert.equal(calls.length, 1);
  const html = await readFile(join(dir, 'catalog', '17', 'index.html'), 'utf8');
  assert.match(html, /<title>Монета &lt;Ріка&gt; — Bakost Numismatics<\/title>/);
  assert.match(html, /rel="canonical" href="https:\/\/example.test\/catalog\/17"/);
  assert.match(html, /Україна · 2020 · 5 гривень · Природа/);
  assert.doesNotMatch(html, /9999|private-source|marketPrice/);
  assert.match(await readFile(join(dir, 'sitemap.xml'), 'utf8'), /catalog\/17/);
  assert.match(await readFile(join(dir, 'robots.txt'), 'utf8'), /sitemap.xml/);
});

test('updates the production HTML template metadata', async () => {
  const source = await readFile(fileURLToPath(new URL('../index.html', import.meta.url)), 'utf8');
  const dir = await mkdtemp(join(tmpdir(), 'bakost-seo-template-'));
  await writeFile(join(dir, 'index.html'), source);
  await prerenderCatalog({
    siteUrl: 'https://example.test',
    distDir: dir,
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({
        total: 1,
        items: [{ id: 2, title: 'Журавель', country: 'Україна', year: 2024 }],
      }),
    }),
  });
  const html = await readFile(join(dir, 'catalog', '2', 'index.html'), 'utf8');
  assert.match(html, /<meta name="description" content="Монета Журавель/);
  assert.match(html, /<meta property="og:title" content="Журавель — Bakost Numismatics"/);
  assert.match(
    html,
    /<meta property="og:image" content="https:\/\/example.test\/brand\/logo-full-1600.png"/,
  );
});
