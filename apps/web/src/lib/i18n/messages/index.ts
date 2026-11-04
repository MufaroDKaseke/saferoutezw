import type { Locale } from "../config";
import type { Messages } from "../translate";
import { en } from "./en";
import { nd } from "./nd";
import { sn } from "./sn";

/** Server-side lookup of every language. Client code never imports this: it receives one language from the layout. */
export const MESSAGES: Record<Locale, Messages> = { en, sn, nd };
