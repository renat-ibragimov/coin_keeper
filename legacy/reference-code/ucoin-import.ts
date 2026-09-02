import { BrowserWindow } from "electron";
import type { CoinInput, PriceRefreshResult, UcoinImportResult } from "../domain/types";
import type { DatabaseService, ImportedCatalogRow } from "./database";

interface ExtractedImage {
  src: string;
  alt: string;
  width: number;
  height: number;
}

interface ExtractedPage {
  url: string;
  heading: string;
  subtitle: string;
  info: Record<string, string>;
  priceText: string;
  images: ExtractedImage[];
  coinLinks: string[];
  pageLinks: string[];
  bodyText: string;
}

function cleanText(value: unknown): string {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function isUcoinUrl(url: URL): boolean {
  return /(^|\.)ucoin\.net$/i.test(url.hostname);
}

export function canonicalUrl(value: string): string {
  const url = new URL(value);
  if (isUcoinUrl(url)) {
    url.protocol = "https:";
    url.hostname = "uk.ucoin.net";
  }
  url.hash = "";
  return url.toString();
}

export function sourceKeyFor(url: string): string {
  const parsed = new URL(url);
  if (isUcoinUrl(parsed)) parsed.hostname = "ru.ucoin.net";
  return `ucoin:${parsed.hostname}${parsed.pathname}${parsed.searchParams.get("tid") ? `?tid=${parsed.searchParams.get("tid")}` : ""}`;
}

export function parsePriceUah(value: string): number | null {
  const text = cleanText(value);
  if (!/(?:₴|грн\.?|UAH)/i.test(text) || /\*{2,}/.test(text) || /[=x]/i.test(text)) return null;
  const match = text.match(/(\d[\d\s.,]*)\s*(?:₴|грн\.?|UAH)/i);
  const digits = match?.[1]?.replace(/[^\d]/g, "") ?? "";
  return digits ? Number(digits) : null;
}

function classifyGroup(value: string): CoinInput["collectionGroup"] {
  return /регуляр|обиход|обігов|circulation/i.test(value) ? "circulation" : "commemorative";
}

function infoValue(info: Record<string, string>, keys: string[]): string {
  for (const key of keys) {
    const value = info[key];
    if (value) return value;
  }
  return "";
}

function pickImage(images: ExtractedImage[], role: "obverse" | "reverse"): string | null {
  const pattern = role === "obverse" ? /obverse|аверс/i : /reverse|реверс/i;
  const direct = images.find((image) => pattern.test(image.alt));
  if (direct) return direct.src;
  const coinImages = images.filter((image) => !/logo|avatar|flag|ucoin/i.test(image.alt) && !/logo|avatar|flag/i.test(image.src));
  return coinImages[role === "obverse" ? 0 : 1]?.src ?? null;
}

function coinInputFromPage(page: ExtractedPage, sourceUrl: string): CoinInput {
  const info = page.info;
  const headingMatch = page.heading.match(/(.+?)\s+(.+?),\s*(\d{4})/);
  const title = cleanText(infoValue(info, ["Наименование", "Найменування", "Subject"]) || page.subtitle || page.heading);
  const country = cleanText(infoValue(info, ["Страна", "Країна", "Country"]) || headingMatch?.[1] || "США");
  const denomination = cleanText(infoValue(info, ["Номинал", "Номінал", "Denomination"]) || headingMatch?.[2] || "1 доллар");
  const year = Number(cleanText(infoValue(info, ["Год", "Рік", "Year"]) || headingMatch?.[3] || new Date().getFullYear()));
  const price = parsePriceUah(page.priceText);
  const obverseImageUrl = pickImage(page.images, "obverse");
  const reverseImageUrl = pickImage(page.images, "reverse");

  return {
    country,
    seriesName: cleanText(infoValue(info, ["Серия", "Серія", "Series"]) || infoValue(info, ["Период", "Період", "Period"]) || ""),
    denomination,
    year: Number.isFinite(year) ? year : new Date().getFullYear(),
    title,
    variety: "",
    catalogNumber: cleanText(infoValue(info, ["Номер", "Number"])),
    collectionGroup: classifyGroup(cleanText(infoValue(info, ["Вид чекана", "Тип монеты", "Тип монети", "Coin type"]))),
    material: cleanText(infoValue(info, ["Материал", "Матеріал", "Composition"])),
    marketPriceUah: price,
    priceSource: "uCoin",
    sourceUrl: canonicalUrl(sourceUrl),
    obverseImageUrl,
    reverseImageUrl,
  };
}

export class UcoinImportService {
  constructor(private readonly database: DatabaseService) {}

  async previewCoin(url: string): Promise<CoinInput> {
    const page = await this.loadPage(canonicalUrl(url));
    if (!infoValue(page.info, ["Номер", "Number"]) && !infoValue(page.info, ["Наименование", "Найменування", "Subject"])) {
      throw new Error("Не удалось распознать карточку монеты uCoin. Проверьте ссылку.");
    }
    return coinInputFromPage(page, page.url);
  }

  async importUrl(url: string): Promise<UcoinImportResult> {
    const canonical = canonicalUrl(url);
    if (new URL(canonical).pathname.includes("/coin/")) {
      const input = await this.previewCoin(canonical);
      const result = this.database.importCatalogRows([{ ...input, sourceKey: sourceKeyFor(canonical) }]);
      return { mode: "coin", sourceUrl: canonical, scanned: 1, inserted: result.inserted, updated: result.updated, skipped: result.skipped, warnings: [] };
    }

    const links = await this.collectCatalogCoinLinks(canonical);
    const rows: ImportedCatalogRow[] = [];
    const warnings: string[] = [];
    for (const link of links) {
      try {
        const input = await this.previewCoin(link);
        rows.push({ ...input, sourceKey: sourceKeyFor(link) });
        await new Promise((resolve) => setTimeout(resolve, 450));
      } catch (error) {
        warnings.push(`${link}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    const result = this.database.importCatalogRows(rows);
    return { mode: "catalog", sourceUrl: canonical, scanned: links.length, inserted: result.inserted, updated: result.updated, skipped: result.skipped, warnings };
  }

  async refreshCoinPrice(id: number): Promise<PriceRefreshResult> {
    const coin = this.database.getCatalogCoin(id);
    const observedAt = new Date().toISOString();
    if (!coin.sourceUrl || !coin.sourceUrl.includes("ucoin.net")) {
      return {
        catalogItemId: id,
        source: "uCoin",
        status: "not-found",
        previousPriceUah: coin.marketPriceUah,
        priceUah: coin.marketPriceUah,
        observedAt,
        message: "Для этой монеты не сохранена ссылка uCoin.",
      };
    }

    const page = await this.loadPage(canonicalUrl(coin.sourceUrl));
    const price = parsePriceUah(page.priceText);
    if (price === null) {
      return {
        catalogItemId: id,
        source: "uCoin",
        status: "not-found",
        previousPriceUah: coin.marketPriceUah,
        priceUah: coin.marketPriceUah,
        observedAt,
        sourceUrl: page.url,
        message: "Цена на странице uCoin не найдена.",
      };
    }

    this.database.saveMarketPrice(id, price, "uCoin", observedAt, page.url);
    return {
      catalogItemId: id,
      source: "uCoin",
      status: "updated",
      previousPriceUah: coin.marketPriceUah,
      priceUah: price,
      observedAt,
      sourceUrl: page.url,
      message: `Цена uCoin обновлена: ${price.toLocaleString("uk-UA")} грн.`,
    };
  }

  private async collectCatalogCoinLinks(url: string): Promise<string[]> {
    const firstPage = await this.loadPage(url);
    const pages = new Set([firstPage.url, ...firstPage.pageLinks]);
    const links = new Set(firstPage.coinLinks);

    for (const pageUrl of [...pages]) {
      if (pageUrl === firstPage.url) continue;
      const page = await this.loadPage(pageUrl);
      for (const link of page.coinLinks) links.add(link);
      await new Promise((resolve) => setTimeout(resolve, 450));
    }
    return [...links];
  }

  private async loadPage(url: string): Promise<ExtractedPage> {
    const pageUrl = canonicalUrl(url);
    const window = new BrowserWindow({
      width: 980,
      height: 760,
      show: false,
      title: "CoinKeeper uCoin import",
      backgroundColor: "#111",
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });

    try {
      window.webContents.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 CoinKeeper/0.1");
      await window.loadURL(pageUrl);
      let page = await this.extractPage(window);
      const started = Date.now();
      while (/just a moment|enable javascript|cloudflare/i.test(page.bodyText) && Date.now() - started < 45_000) {
        if (!window.isVisible()) window.show();
        await new Promise((resolve) => setTimeout(resolve, 1500));
        page = await this.extractPage(window);
      }
      if (/just a moment|enable javascript|cloudflare/i.test(page.bodyText)) {
        throw new Error("uCoin не отдал страницу из-за проверки Cloudflare. Откройте окно проверки и повторите импорт.");
      }
      return page;
    } finally {
      if (!window.isDestroyed()) window.close();
    }
  }

  private async extractPage(window: BrowserWindow): Promise<ExtractedPage> {
    return window.webContents.executeJavaScript(`
      (() => {
        const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
        const absolute = (value) => {
          try { return new URL(value, location.href).toString(); } catch { return ""; }
        };
        const info = {};
        document.querySelectorAll("table tr").forEach((row) => {
          const cells = Array.from(row.children).map((cell) => clean(cell.innerText || cell.textContent));
          if (cells.length >= 2 && cells[0]) info[cells[0].replace(/:$/, "")] = cells.slice(1).join(" ");
        });
        const allTextNodes = Array.from(document.querySelectorAll("body *")).map((element) => clean(element.innerText || element.textContent)).filter(Boolean);
        const pricePattern = /^\\d[\\d\\s.,]*\\s*(?:₴|грн\\.?|UAH)$/i;
        const priceText = allTextNodes.find((text) => pricePattern.test(text) && !/[=x]/i.test(text)) || "";
        const heading = clean(document.querySelector("h1")?.innerText) || allTextNodes.find((text) => /^.{2,40},\\s*\\d{4}$/.test(text)) || "";
        const subtitle = clean(document.querySelector("h1")?.nextElementSibling?.textContent) || "";
        const images = Array.from(document.images).map((image) => ({
          src: absolute(image.currentSrc || image.src),
          alt: clean(image.alt || image.title),
          width: image.naturalWidth || image.width || 0,
          height: image.naturalHeight || image.height || 0,
        })).filter((image) => image.src);
        const coinLinks = [...new Set(Array.from(document.querySelectorAll('a[href*="/coin/"]')).map((a) => absolute(a.getAttribute("href"))).filter(Boolean))];
        const pageLinks = [...new Set(Array.from(document.querySelectorAll('a[href*="page="], a[href*="&p="], a[href*="?p="]')).map((a) => absolute(a.getAttribute("href"))).filter((href) => href.includes("/catalog/")))];
        return { url: location.href, heading, subtitle, info, priceText, images, coinLinks, pageLinks, bodyText: clean(document.body?.innerText) };
      })()
    `) as Promise<ExtractedPage>;
  }
}
