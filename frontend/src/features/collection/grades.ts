/** Grades offered in the purchase form; the API stores any free text. */
export const GRADES = ['UNC', 'BU', 'PROOF', 'PL', 'AU', 'XF', 'VF', 'F', 'VG', 'G'] as const;

/** Default grade by the catalog group (docs/04-business-rules.md, rule 7). */
export function defaultGradeFor(
  group: string | null | undefined,
  settings: { defaultGradeCommemorative: string; defaultGradeCirculation: string },
): string {
  return group === 'circulation'
    ? settings.defaultGradeCirculation
    : settings.defaultGradeCommemorative;
}
