import { ZipArchive } from "archiver";
import { createHash, randomUUID } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import type { BackupListItem, BackupResult } from "../domain/types";
import type { DatabaseService } from "./database";

interface BackupPaths {
  backupsDirectory: string;
  mediaDirectory: string;
  tempDirectory: string;
}

function timestampForFile(date: Date): string {
  return date.toISOString().replaceAll(":", "-").replace(".000Z", "Z");
}

async function sha256(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);
    stream.on("error", reject);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

export class BackupService {
  constructor(
    private readonly database: DatabaseService,
    private readonly paths: BackupPaths,
    private readonly appVersion: string,
  ) {}

  async create(): Promise<BackupResult> {
    const createdAt = new Date();
    await fs.mkdir(this.paths.backupsDirectory, { recursive: true });
    await fs.mkdir(this.paths.tempDirectory, { recursive: true });

    const fileName = `CoinKeeper-backup-${timestampForFile(createdAt)}.zip`;
    const absolutePath = path.join(this.paths.backupsDirectory, fileName);
    const snapshotPath = path.join(this.paths.tempDirectory, `snapshot-${randomUUID()}.db`);
    const runId = this.database.recordBackupStart(absolutePath);

    try {
      this.database.createSnapshot(snapshotPath);
      const databaseChecksum = await sha256(snapshotPath);
      const manifest = {
        format: "coinkeeper-backup",
        formatVersion: 1,
        appVersion: this.appVersion,
        schemaVersion: this.database.getSchemaVersion(),
        createdAt: createdAt.toISOString(),
        databaseSha256: databaseChecksum,
      };

      await new Promise<void>((resolve, reject) => {
        const output = createWriteStream(absolutePath);
        const archive = new ZipArchive({ zlib: { level: 9 } });
        output.on("close", resolve);
        output.on("error", reject);
        archive.on("warning", (error: Error & { code?: string }) => {
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") reject(error);
        });
        archive.on("error", reject);
        archive.pipe(output);
        archive.file(snapshotPath, { name: "database/coinkeeper.db" });
        archive.directory(this.paths.mediaDirectory, "media");
        archive.append(JSON.stringify(manifest, null, 2), { name: "manifest.json" });
        void archive.finalize();
      });

      const fileStats = await fs.stat(absolutePath);
      const checksum = await sha256(absolutePath);
      this.database.recordBackupComplete(runId, checksum, fileStats.size);

      return {
        fileName,
        absolutePath,
        sizeBytes: fileStats.size,
        createdAt: createdAt.toISOString(),
        checksum,
      };
    } catch (error) {
      this.database.recordBackupFailure(runId, error instanceof Error ? error.message : String(error));
      await fs.rm(absolutePath, { force: true });
      throw error;
    } finally {
      await fs.rm(snapshotPath, { force: true });
    }
  }

  async list(): Promise<BackupListItem[]> {
    await fs.mkdir(this.paths.backupsDirectory, { recursive: true });
    const entries = await fs.readdir(this.paths.backupsDirectory, { withFileTypes: true });
    const backups = await Promise.all(
      entries
        .filter((entry) => entry.isFile() && entry.name.endsWith(".zip"))
        .map(async (entry) => {
          const absolutePath = path.join(this.paths.backupsDirectory, entry.name);
          const stats = await fs.stat(absolutePath);
          return {
            fileName: entry.name,
            absolutePath,
            sizeBytes: stats.size,
            createdAt: stats.birthtime.toISOString(),
          };
        }),
    );

    return backups.sort((left, right) => right.createdAt.localeCompare(left.createdAt));
  }
}
