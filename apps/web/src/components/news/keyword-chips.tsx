import { KEYWORD_GROUP_LABEL } from "@/lib/formatters/labels";
import type { KeywordGroup, MatchedKeyword } from "@/types";

const ORDER: KeywordGroup[] = ["incident", "vehicle", "road", "location", "impact"];

/**
 * Matched keywords, grouped. They explain why an article was read further.
 * They do not show that anything happened.
 */
export function KeywordChips({ keywords }: { keywords: MatchedKeyword[] }) {
  if (keywords.length === 0) {
    return <p className="text-sm text-slate-600">No road-safety keywords matched.</p>;
  }
  const groups = ORDER.map((g) => ({ group: g, items: keywords.filter((k) => k.group === g) })).filter((g) => g.items.length);
  return (
    <dl className="space-y-2">
      {groups.map(({ group, items }) => (
        <div key={group} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <dt className="w-16 shrink-0 text-xs font-medium text-slate-600">{KEYWORD_GROUP_LABEL[group]}</dt>
          <dd className="flex flex-wrap gap-1.5">
            {items.map((k) => (
              <span key={k.term} className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-800">
                {k.term}
                {k.occurrences > 1 ? <span className="tnum ml-1 text-slate-500">×{k.occurrences}</span> : null}
              </span>
            ))}
          </dd>
        </div>
      ))}
    </dl>
  );
}
