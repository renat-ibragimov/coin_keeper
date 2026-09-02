import type { PriceRefreshResult, RateRefreshResult, RateSyncResult } from "../domain/types";
import type { DatabaseService } from "./database";

interface NbuRate {
  cc: string;
  rate: number;
  exchangedate: string;
}

function nbuDateToIso(value: string): string {
  const [day, month, year] = value.split(".");
  return `${year}-${month}-${day}`;
}

function todayIso(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function decodeHtml(value: string): string {
  return value
    .replaceAll(/<[^>]+>/g, " ")
    .replaceAll("&thinsp;", " ")
    .replaceAll("&nbsp;", " ")
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", "\"")
    .replaceAll("&#039;", "'")
    .replaceAll(/\s+/g, " ")
    .trim();
}

function normalizeTitle(value: string): string {
  return value
    .toLocaleLowerCase("uk-UA")
    .normalize("NFKD")
    .replaceAll(/[’'`\"«»()[\]{}.,:;!?–—-]/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
}

function denominationValue(value: string): number | null {
  const match = value.replace(",", ".").match(/\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

export function parseUaCoinsPrice(html: string, title: string, denomination: string, sourceUrl: string): { price: number; url: string } | undefined {
  const targetTitle = normalizeTitle(title);
  const targetDenomination = denominationValue(denomination);
  const rows = [...html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi)].map((match) => match[1]);
  for (const row of rows) {
    const titleMatch = row.match(/data-title="Назва"[\s\S]*?<a[^>]*href="\s*([^"\s]+)\s*"[^>]*>([\s\S]*?)<\/a>/i);
    if (!titleMatch) continue;
    const rowTitle = normalizeTitle(decodeHtml(titleMatch[2]));
    const titleMatches = rowTitle === targetTitle || rowTitle.startsWith(`${targetTitle} `) || targetTitle.startsWith(`${rowTitle} `);
    if (!titleMatches) continue;
    const denominationMatch = row.match(/data-title="Номінал"[^>]*>([\s\S]*?)<\/td>/i);
    if (targetDenomination !== null && denominationValue(decodeHtml(denominationMatch?.[1] ?? "")) !== targetDenomination) continue;
    const priceMatch = row.match(/data-title="Вартість [^"]*"[\s\S]*?class="list_price"[^>]*>([\s\S]*?)<\/a>/i);
    const digits = decodeHtml(priceMatch?.[1] ?? "").replaceAll(/[^0-9]/g, "");
    if (!digits) continue;
    return { price: Number(digits), url: new URL(titleMatch[1], sourceUrl).toString() };
  }
  return undefined;
}

function parseUaCoinsDetailPrice(html: string): number | null {
  const text = html
    .replaceAll(/<script[\s\S]*?<\/script>/gi, " ")
    .replaceAll(/<style[\s\S]*?<\/style>/gi, " ")
    .replaceAll(/<[^>]+>/g, " ")
    .replaceAll("&nbsp;", " ")
    .replaceAll(/\s+/g, " ");
  const candidates = [...text.matchAll(/(\d[\d\s.,]{1,12})\s*(?:грн|₴|UAH)/gi)]
    .map((match) => Number(match[1].replace(/[^\d]/g, "")))
    .filter((value) => Number.isFinite(value) && value > 0);
  return candidates[0] ?? null;
}

export class PricingService {
  constructor(private readonly database: DatabaseService) {}

  async refreshRates(): Promise<RateRefreshResult> {
    return this.fetchRates();
  }

  async refreshRatesForDate(date: string): Promise<RateRefreshResult> {
    return this.fetchRates(date);
  }

  async syncMissingRates(startDate = "2009-01-01", endDate = todayIso()): Promise<RateSyncResult> {
    const dates = this.database.listMissingExchangeRateDates(startDate, endDate);
    const failedDates: RateSyncResult["failedDates"] = [];
    let fetchedDates = 0;

    for (const date of dates) {
      try {
        await this.fetchRates(date);
        fetchedDates += 1;
      } catch (error) {
        failedDates.push({ date, message: error instanceof Error ? error.message : String(error) });
      }
    }

    return { startDate, endDate, checkedDates: dates.length, fetchedDates, failedDates };
  }

  private async fetchRates(date?: string): Promise<RateRefreshResult> {
    const dateQuery = date ? `&date=${date.replaceAll("-", "")}` : "";
    const response = await fetch(`https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json${dateQuery}`);
    if (!response.ok) throw new Error(`НБУ вернул HTTP ${response.status}`);
    const payload = await response.json() as NbuRate[];
    const selected = (["USD", "EUR"] as const).map((code) => {
      const rate = payload.find((item) => item.cc === code);
      if (!rate) throw new Error(`НБУ не вернул курс ${code}`);
      const effectiveDate = nbuDateToIso(rate.exchangedate);
      this.database.saveExchangeRate(code, rate.rate, effectiveDate);
      return { code, rate: rate.rate, effectiveDate };
    });
    return { effectiveDate: selected[0].effectiveDate, rates: selected.map(({ code, rate }) => ({ code, rate })) };
  }

  async refreshCoinPrice(id: number): Promise<PriceRefreshResult> {
    const coin = this.database.getCatalogCoin(id);
    const observedAt = new Date().toISOString();
    if (coin.sourceUrl?.includes("ua-coins.info")) {
      const response = await fetch(coin.sourceUrl, { headers: { "User-Agent": "CoinKeeper/0.1 personal collection" } });
      if (!response.ok) throw new Error(`UA-Coins вернул HTTP ${response.status}`);
      const price = parseUaCoinsDetailPrice(await response.text());
      if (price === null) {
        return {
          catalogItemId: id,
          source: "UA-Coins",
          status: "not-found",
          previousPriceUah: coin.marketPriceUah,
          priceUah: coin.marketPriceUah,
          observedAt,
          sourceUrl: coin.sourceUrl,
          message: "Цена на сохранённой странице UA-Coins не найдена.",
        };
      }
      this.database.saveMarketPrice(id, price, "UA-Coins", observedAt, coin.sourceUrl);
      return {
        catalogItemId: id,
        source: "UA-Coins",
        status: "updated",
        previousPriceUah: coin.marketPriceUah,
        priceUah: price,
        observedAt,
        sourceUrl: coin.sourceUrl,
        message: `Цена UA-Coins обновлена: ${price.toLocaleString("uk-UA")} грн.`,
      };
    }

    if (coin.country !== "Украина") {
      return {
        catalogItemId: id,
        source: "Numista",
        status: "needs-api-key",
        previousPriceUah: coin.marketPriceUah,
        priceUah: coin.marketPriceUah,
        observedAt,
        message: "Для Numista нужен персональный API-ключ. Без ключа запросы официально не принимаются.",
      };
    }

    const sourceUrl = `https://www.ua-coins.info/ua/catalog/all/${coin.year}`;
    const response = await fetch(sourceUrl, { headers: { "User-Agent": "CoinKeeper/0.1 personal collection" } });
    if (!response.ok) throw new Error(`UA-Coins вернул HTTP ${response.status}`);
    const html = await response.text();
    const matched = parseUaCoinsPrice(html, coin.title, coin.denomination, sourceUrl);

    if (!matched) {
      return {
        catalogItemId: id,
        source: "UA-Coins",
        status: "not-found",
        previousPriceUah: coin.marketPriceUah,
        priceUah: coin.marketPriceUah,
        observedAt,
        sourceUrl,
        message: "Точное совпадение названия, года и номинала на UA-Coins не найдено.",
      };
    }

    this.database.saveMarketPrice(id, matched.price, "UA-Coins", observedAt, matched.url);
    return {
      catalogItemId: id,
      source: "UA-Coins",
      status: "updated",
      previousPriceUah: coin.marketPriceUah,
      priceUah: matched.price,
      observedAt,
      sourceUrl: matched.url,
      message: `Цена обновлена: ${matched.price.toLocaleString("uk-UA")} грн.`,
    };
  }
}
