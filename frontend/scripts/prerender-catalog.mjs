/** Build public, crawlable catalog HTML from the same anonymous API as the SPA. */
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const escapeHtml = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (character) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[character],
  );

function replaceMeta(html, kind, name, value) {
  const attribute = kind === 'property' ? 'property' : 'name';
  const pattern = new RegExp(`<meta\\s+${attribute}="${name}"\\s+content="[^"]*"\\s*/?>`, 'i');
  return html.replace(pattern, `<meta ${attribute}="${name}" content="${escapeHtml(value)}" />`);
}

export function renderPage(
  template,
  { title, description, canonical, siteUrl, body, type = 'article' },
) {
  let html = template.replace(/<title>[^<]*<\/title>/i, `<title>${escapeHtml(title)}</title>`);
  html = replaceMeta(html, 'name', 'description', description);
  html = replaceMeta(html, 'property', 'og:title', title);
  html = replaceMeta(html, 'property', 'og:description', description);
  html = replaceMeta(html, 'property', 'og:type', type);
  html = replaceMeta(html, 'property', 'og:image', `${siteUrl}/brand/logo-full-1600.png`);
  html = html.replace(
    '</head>',
    `<link rel="canonical" href="${escapeHtml(canonical)}" />\n<meta property="og:url" content="${escapeHtml(canonical)}" />\n</head>`,
  );
  return html.replace('<div id="root"></div>', `<div id="root">${body}</div>`);
}

function coinText(item) {
  const denomination = item.denomination?.label ?? item.denominationText;
  return [
    item.country,
    item.year,
    denomination,
    item.seriesName,
    item.composition?.name ?? item.material,
  ]
    .filter((value) => value !== null && value !== undefined && value !== '')
    .join(' · ');
}

export async function prerenderCatalog({ siteUrl, distDir, fetchImpl = fetch }) {
  const origin = new URL(siteUrl);
  if (
    origin.pathname !== '/' ||
    origin.search ||
    origin.hash ||
    !['https:', 'http:'].includes(origin.protocol)
  ) {
    throw new Error('SITE_URL must be an origin without a path or query string');
  }
  const site = origin.origin;
  const template = await readFile(join(distDir, 'index.html'), 'utf8');
  const items = [];
  for (let page = 1; page <= 1000; page++) {
    const response = await fetchImpl(
      `${site}/api/v1/catalog?page=${page}&pageSize=200&scope=shared&sort=title`,
    );
    if (!response.ok) throw new Error(`Public catalog request failed: HTTP ${response.status}`);
    const batch = await response.json();
    if (!Array.isArray(batch.items) || !Number.isInteger(batch.total)) {
      throw new Error('Unexpected public catalog response');
    }
    items.push(...batch.items);
    if (items.length >= batch.total) break;
    if (batch.items.length === 0) throw new Error('Public catalog pagination stopped early');
    if (page === 1000) throw new Error('Public catalog exceeds the prerender safety limit');
  }
  const listingBody = `<main><h1>Каталог монет Bakost Numismatics</h1><p>Переглядайте український нумізматичний каталог.</p><ul>${items.map((item) => `<li><a href="/catalog/${item.id}">${escapeHtml(item.title)}</a></li>`).join('')}</ul></main>`;
  await mkdir(join(distDir, 'catalog'), { recursive: true });
  await writeFile(
    join(distDir, 'catalog', 'index.html'),
    renderPage(template, {
      title: 'Каталог монет — Bakost Numismatics',
      description:
        'Публічний український каталог монет Bakost Numismatics: випуски, серії та характеристики.',
      canonical: `${site}/catalog`,
      siteUrl: site,
      body: listingBody,
      type: 'website',
    }),
  );
  for (const item of items) {
    if (!Number.isSafeInteger(item.id) || item.id <= 0)
      throw new Error('Invalid public catalog id');
    const title = `${item.title} — Bakost Numismatics`;
    const description = `Монета ${item.title}. ${coinText(item)}. Характеристики у каталозі Bakost Numismatics.`;
    const body = `<main><article><h1>${escapeHtml(item.title)}</h1><p>${escapeHtml(coinText(item))}</p><p><a href="/catalog">Каталог монет</a></p></article></main>`;
    const dir = join(distDir, 'catalog', String(item.id));
    await mkdir(dir, { recursive: true });
    await writeFile(
      join(dir, 'index.html'),
      renderPage(template, {
        title,
        description,
        canonical: `${site}/catalog/${item.id}`,
        siteUrl: site,
        body,
      }),
    );
  }
  const locations = ['/catalog', ...items.map((item) => `/catalog/${item.id}`)];
  await writeFile(
    join(distDir, 'sitemap.xml'),
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${locations.map((path) => `<url><loc>${escapeHtml(site + path)}</loc></url>`).join('')}</urlset>\n`,
  );
  await writeFile(
    join(distDir, 'robots.txt'),
    `User-agent: *\nAllow: /catalog\nDisallow: /api/\nDisallow: /admin\nDisallow: /collection\nDisallow: /settings\nDisallow: /login\nDisallow: /register\nDisallow: /verify-email\nDisallow: /reset-password\nSitemap: ${site}/sitemap.xml\n`,
  );
  return items.length;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const siteUrl = process.env.SITE_URL;
  if (!siteUrl) throw new Error('SITE_URL is required');
  const count = await prerenderCatalog({ siteUrl, distDir: process.env.DIST_DIR ?? 'dist' });
  process.stdout.write(`Prerendered ${count} public catalog pages\n`);
}
