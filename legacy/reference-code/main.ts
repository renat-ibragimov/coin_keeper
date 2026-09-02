import { app, BrowserWindow, dialog, ipcMain } from "electron";
import fs from "node:fs/promises";
import path from "node:path";
import { BackupService } from "./services/backup";
import { DatabaseService } from "./services/database";
import { ExcelImportService } from "./services/excel-import";
import { PricingService } from "./services/pricing";
import { UcoinImportService } from "./services/ucoin-import";
import type { CoinInput, PurchaseInput } from "./domain/types";

let database: DatabaseService | undefined;
let backupService: BackupService | undefined;
let excelImportService: ExcelImportService | undefined;
let pricingService: PricingService | undefined;
let ucoinImportService: UcoinImportService | undefined;

function getDataDirectory(): string {
  const explicitDataDirectory = process.env.COINKEEPER_DATA_DIR;
  if (explicitDataDirectory) return path.resolve(explicitDataDirectory);
  const portableFile = process.env.PORTABLE_EXECUTABLE_FILE;
  const portableRoot = process.env.PORTABLE_EXECUTABLE_DIR ?? (portableFile ? path.dirname(portableFile) : undefined);
  if (portableRoot) return path.join(portableRoot, "CoinKeeper Data");
  if (app.isPackaged) return path.join(path.dirname(app.getPath("exe")), "CoinKeeper Data");
  return path.join(app.getPath("userData"), "CoinKeeper Data");
}

async function createWindow(): Promise<void> {
  const window = new BrowserWindow({
    width: 1480,
    height: 940,
    minWidth: 1120,
    minHeight: 720,
    show: false,
    backgroundColor: "#08090b",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#08090b",
      symbolColor: "#8e929b",
      height: 44,
    },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  window.once("ready-to-show", () => window.show());

  if (process.argv.includes("--dev")) {
    await window.loadURL("http://127.0.0.1:5173");
  } else {
    await window.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  if (process.argv.includes("--capture")) {
    await new Promise((resolve) => setTimeout(resolve, 1600));
    const image = await window.webContents.capturePage();
    const outputDirectory = path.join(process.cwd(), "artifacts", "screenshots");
    await fs.mkdir(outputDirectory, { recursive: true });
    await fs.writeFile(path.join(outputDirectory, "dashboard.png"), image.toPNG());
    app.quit();
  }
}

function registerIpc(dataDirectory: string): void {
  ipcMain.handle("app:bootstrap", () => ({
    appVersion: app.getVersion(),
    dataDirectory,
    schemaVersion: database!.getSchemaVersion(),
    dashboard: database!.getDashboardSnapshot(),
    exchangeRates: database!.getLatestExchangeRates(),
    finance: database!.getFinanceSummary(),
  }));
  ipcMain.handle("backup:create", () => backupService!.create());
  ipcMain.handle("backup:list", () => backupService!.list());
  ipcMain.handle("catalog:list", () => database!.listCatalog());
  ipcMain.handle("catalog:create", (_event, input: CoinInput) => database!.createCoin(input));
  ipcMain.handle("catalog:update", (_event, id: number, input: CoinInput) => database!.updateCoin(id, input));
  ipcMain.handle("catalog:delete", (_event, id: number) => database!.deleteCoin(id));
  ipcMain.handle("purchase:list", (_event, catalogItemId: number) => database!.listPurchases(catalogItemId));
  ipcMain.handle("price-history:list", (_event, catalogItemId: number) => database!.listPriceHistory(catalogItemId));
  ipcMain.handle("purchase:create", async (_event, input: PurchaseInput) => {
    try {
      await pricingService!.refreshRatesForDate(input.purchaseDate);
    } catch (error) {
      console.warn("Historical NBU rate could not be refreshed; the UAH purchase will still be saved.", error);
    }
    return database!.addPurchase(input);
  });
  ipcMain.handle("rates:refresh", () => pricingService!.refreshRates());
  ipcMain.handle("rates:sync-missing", () => pricingService!.syncMissingRates());
  ipcMain.handle("price:refresh", async (_event, id: number) => {
    const coin = database!.getCatalogCoin(id);
    if (coin.sourceUrl?.includes("ucoin.net")) return ucoinImportService!.refreshCoinPrice(id);
    return pricingService!.refreshCoinPrice(id);
  });
  ipcMain.handle("ucoin:preview-coin", (_event, url: string) => ucoinImportService!.previewCoin(url));
  ipcMain.handle("ucoin:import-url", (_event, url: string) => ucoinImportService!.importUrl(url));
  ipcMain.handle("excel:import", (_event, filePaths: string[]) => excelImportService!.importFiles(filePaths));
  ipcMain.handle("excel:select", async () => {
    const result = await dialog.showOpenDialog({
      title: "Выберите Excel-файлы",
      properties: ["openFile", "multiSelections"],
      filters: [{ name: "Excel", extensions: ["xlsx", "xls"] }],
    });
    return result.canceled ? [] : result.filePaths;
  });
}

app.whenReady().then(async () => {
  const dataDirectory = getDataDirectory();
  if (process.argv.includes("--capture")) {
    await fs.writeFile(
      path.join(app.getPath("temp"), "CoinKeeper-portable-trace.json"),
      JSON.stringify({
        portableDirectory: process.env.PORTABLE_EXECUTABLE_DIR ?? null,
        portableFile: process.env.PORTABLE_EXECUTABLE_FILE ?? null,
        executable: app.getPath("exe"),
        dataDirectory,
        workingDirectory: process.cwd(),
        arguments: process.argv,
        packaged: app.isPackaged,
      }, null, 2),
    );
  }
  const mediaDirectory = path.join(dataDirectory, "media");
  const backupsDirectory = path.join(dataDirectory, "backups");
  const tempDirectory = path.join(dataDirectory, "temp");
  await Promise.all([
    fs.mkdir(mediaDirectory, { recursive: true }),
    fs.mkdir(backupsDirectory, { recursive: true }),
    fs.mkdir(tempDirectory, { recursive: true }),
  ]);

  database = new DatabaseService(path.join(dataDirectory, "coinkeeper.db"));
  backupService = new BackupService(database, { backupsDirectory, mediaDirectory, tempDirectory }, app.getVersion());
  excelImportService = new ExcelImportService(database);
  pricingService = new PricingService(database);
  ucoinImportService = new UcoinImportService(database);
  registerIpc(dataDirectory);
  await createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) void createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => database?.close());
