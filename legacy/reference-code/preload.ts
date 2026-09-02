import { contextBridge, ipcRenderer } from "electron";
import type { CoinKeeperApi } from "./domain/types";

const api: CoinKeeperApi = {
  getBootstrap: () => ipcRenderer.invoke("app:bootstrap"),
  createBackup: () => ipcRenderer.invoke("backup:create"),
  listBackups: () => ipcRenderer.invoke("backup:list"),
  selectExcelFiles: () => ipcRenderer.invoke("excel:select"),
  importExcel: (filePaths) => ipcRenderer.invoke("excel:import", filePaths),
  listCatalog: () => ipcRenderer.invoke("catalog:list"),
  createCoin: (input) => ipcRenderer.invoke("catalog:create", input),
  updateCoin: (id, input) => ipcRenderer.invoke("catalog:update", id, input),
  deleteCoin: (id) => ipcRenderer.invoke("catalog:delete", id),
  addPurchase: (input) => ipcRenderer.invoke("purchase:create", input),
  listPurchases: (catalogItemId) => ipcRenderer.invoke("purchase:list", catalogItemId),
  listPriceHistory: (catalogItemId) => ipcRenderer.invoke("price-history:list", catalogItemId),
  refreshRates: () => ipcRenderer.invoke("rates:refresh"),
  syncMissingRates: () => ipcRenderer.invoke("rates:sync-missing"),
  refreshCoinPrice: (id) => ipcRenderer.invoke("price:refresh", id),
  previewUcoinCoin: (url) => ipcRenderer.invoke("ucoin:preview-coin", url),
  importUcoinUrl: (url) => ipcRenderer.invoke("ucoin:import-url", url),
};

contextBridge.exposeInMainWorld("coinKeeper", api);
