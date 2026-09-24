import { todayIso } from '@/shared/lib/format';

/**
 * What survives switching the type on the "Додати" form.
 *
 * The five fields both branches have in common under different names: a
 * purchase calls them price / currency / date / seller / note, an expense
 * amount / currency / date / vendor / description. Someone who typed the
 * sum and the date and then realised they had picked the wrong type should
 * not have to type them again (docs/ui.md).
 */
export interface CarriedValues {
  amount: string;
  currency: string;
  date: string;
  vendor: string;
  note: string;
}

export function emptyCarried(): CarriedValues {
  return { amount: '', currency: 'UAH', date: todayIso(), vendor: '', note: '' };
}
