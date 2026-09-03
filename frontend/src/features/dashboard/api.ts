import { api } from '@/shared/api/client';
import type { BootstrapOut } from '@/shared/api/types';

/** One request feeds the whole overview (docs/03-api-contract.md, Bootstrap). */
export function fetchBootstrap(): Promise<BootstrapOut> {
  return api<BootstrapOut>('/bootstrap');
}
