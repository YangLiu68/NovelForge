// Why a fact whose quote does not name its character was attributed to that character
// (rules-v4 and later record it in claim.details.resolved).

export interface Resolvable {
  details: Record<string, unknown> | null | undefined;
  subject_name: string;
}

export function resolvedNote(item: Resolvable): string | null {
  const r = item.details?.resolved as { via?: string; pronoun?: string } | undefined;
  if (!r) return null;
  if (r.pronoun) {
    return `Attributed through “${r.pronoun}”: ${item.subject_name} is the only character it can mean nearby. Check before accepting.`;
  }
  return `Attributed to ${item.subject_name} as the subject of the sentence. Check before accepting.`;
}
