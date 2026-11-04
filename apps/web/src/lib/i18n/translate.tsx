import { Fragment, type ReactNode } from "react";
import type { Locale } from "./config";
import { en } from "./messages/en";

export type MessageKey = keyof typeof en;
/** Every language must provide every key; a missing translation is a type error, not a blank on screen. */
export type Messages = Record<MessageKey, string>;

/** Keys written as "name.one" and "name.other" are addressed as "name" and chosen by `count`. */
type BaseKey<K extends string> = K extends `${infer B}.${"one" | "other"}` ? B : K;
export type TranslationKey = BaseKey<MessageKey>;

export type Params = Record<string, string | number>;
export type RichTags = Record<string, (chunks: ReactNode) => ReactNode>;

export interface Translator {
  locale: Locale;
  /** Plain text. Pass `count` to pick the singular or plural form of a "name.one" / "name.other" pair. */
  t: (key: TranslationKey, params?: Params) => string;
  /** Text with <tag>…</tag> markup mapped to elements, so word order can differ per language. */
  rich: (key: TranslationKey, tags: RichTags, params?: Params) => ReactNode;
  /** Looks up a key built at run time (for example `hazard.${type}`); undefined when it does not exist. */
  maybe: (key: string, params?: Params) => string | undefined;
}

function fill(template: string, params?: Params): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => (name in params ? String(params[name]) : whole));
}

export function createTranslator(locale: Locale, messages: Messages): Translator {
  const table = messages as Record<string, string>;
  const fallback = en as Record<string, string>;

  const lookup = (key: string, params?: Params): string | undefined => {
    let found: string | undefined;
    if (typeof params?.count === "number") {
      const plural = `${key}.${params.count === 1 ? "one" : "other"}`;
      found = table[plural] ?? fallback[plural];
    }
    found ??= table[key] ?? fallback[key];
    return found === undefined ? undefined : fill(found, params);
  };

  const t = (key: TranslationKey, params?: Params) => lookup(key, params) ?? key;

  const rich = (key: TranslationKey, tags: RichTags, params?: Params): ReactNode => {
    const text = t(key, params);
    const out: ReactNode[] = [];
    const pattern = /<(\w+)>([\s\S]*?)<\/\1>/g;
    let last = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(text))) {
      if (match.index > last) out.push(text.slice(last, match.index));
      const render = tags[match[1]];
      out.push(render ? render(match[2]) : match[2]);
      last = match.index + match[0].length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out.map((node, i) => <Fragment key={i}>{node}</Fragment>);
  };

  return { locale, t, rich, maybe: lookup };
}
