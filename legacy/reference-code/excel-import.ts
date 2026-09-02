import ExcelJS from "exceljs";
import path from "node:path";
import type { ImportSummary } from "../domain/types";
import type { DatabaseService, ImportedCatalogRow } from "./database";

function asText(value: ExcelJS.CellValue): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") {
    if ("text" in value && typeof value.text === "string") return value.text;
    if ("result" in value && value.result !== undefined) return String(value.result ?? "");
    if ("richText" in value && Array.isArray(value.richText)) return value.richText.map((item) => item.text).join("");
  }
  return String(value).trim();
}

function asNumber(value: ExcelJS.CellValue): number | null {
  const text = asText(value).replaceAll(" ", "").replace(",", ".");
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizedKey(parts: Array<string | number | null>): string {
  return parts.map((part) => String(part ?? "").trim().toLocaleLowerCase()).join("|");
}

function groupFor(denomination: string, title: string): ImportedCatalogRow["collectionGroup"] {
  const value = Number(denomination.match(/\d+(?:[.,]\d+)?/)?.[0]?.replace(",", ".") ?? 0);
  if (title && /грив/i.test(denomination) && value >= 2) return "commemorative";
  return "circulation";
}

export class ExcelImportService {
  constructor(private readonly database: DatabaseService) {}

  async importFiles(filePaths: string[]): Promise<ImportSummary[]> {
    const summaries: ImportSummary[] = [];
    for (const filePath of filePaths) summaries.push(await this.importFile(filePath));
    return summaries;
  }

  private async importFile(filePath: string): Promise<ImportSummary> {
    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.readFile(filePath);
    const sheet = workbook.getWorksheet("Collection");
    if (!sheet) {
      return {
        fileName: path.basename(filePath),
        scanned: 0,
        inserted: 0,
        updated: 0,
        skipped: 0,
        countries: 0,
        warnings: ["Лист Collection не найден. Этот формат пока не распознан."],
      };
    }

    const rows: ImportedCatalogRow[] = [];
    const countries = new Set<string>();
    sheet.eachRow((row, rowNumber) => {
      if (rowNumber === 1) return;
      const country = asText(row.getCell(1).value);
      const seriesName = asText(row.getCell(2).value);
      const denomination = asText(row.getCell(4).value);
      const year = asNumber(row.getCell(5).value);
      if (!country || !denomination || !year) return;
      const variety = asText(row.getCell(6).value);
      const title = asText(row.getCell(7).value);
      const catalogNumber = asText(row.getCell(11).value);
      const marketPriceUah = asNumber(row.getCell(10).value);
      countries.add(country);
      rows.push({
        sourceKey: `ucoin:${normalizedKey([country, denomination, year, variety, title, catalogNumber])}`,
        country,
        seriesName,
        denomination,
        year,
        variety,
        title,
        catalogNumber,
        collectionGroup: groupFor(denomination, title),
        marketPriceUah,
        priceSource: `uCoin Excel · ${path.basename(filePath)}`,
      });
    });

    const result = this.database.importCatalogRows(rows);
    return {
      fileName: path.basename(filePath),
      scanned: rows.length,
      inserted: result.inserted,
      updated: result.updated,
      skipped: result.skipped,
      countries: countries.size,
      warnings: [],
    };
  }
}
