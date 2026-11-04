# Translation review: ChiShona and isiNdebele

The public site is available in English, ChiShona (`sn`) and isiNdebele (`nd`). The ChiShona and
isiNdebele text was drafted by an AI model, not by a native speaker or a professional translator. It
has not been reviewed. Road-safety wording matters, so have a fluent speaker of each language read it
before you promote the languages beyond internal testing.

## Where the text lives

`apps/web/src/lib/i18n/messages/` holds one file per language: `en.ts` (the source), `sn.ts`, `nd.ts`.
Each key is a plain string, so a reviewer can edit the file directly or work from a spreadsheet export.
The type checker fails if `sn.ts` or `nd.ts` lacks a key that `en.ts` has, and a test checks that every
`{placeholder}` and `<tag>` survives translation.

The glossary at the top of `sn.ts` and `nd.ts` lists the terms chosen for notice, alert, editor,
province, hazard and stop. Check those first, because they repeat across the whole site.

## What to look at first

1. The footer disclaimer and "No alert on your route does not mean the road is safe" (`footer.disclaimer`,
   `common.noAlertNotSafe`): safety wording that must not read as reassurance.
2. Severity labels and meanings (`severity.*`).
3. Hazard names (`hazard.*`), which appear on every alert.
4. The subscribe and manage flows (`subscribe.*`, `manage.*`): consent and unsubscribe must be unambiguous.
5. Formality and tone. The draft uses a plain, polite register.

## Not translated yet

Text that does not come from these files stays as the source wrote it:

- Alert headlines, summaries, bodies and the per-alert notice text, written by editors in English.
- Messages the API returns: the SMS/WhatsApp consent wording, "code sent" confirmations, validation
  errors, route duration notes, route warnings and the route disclaimer. The consent text is
  versioned on the server, so translating it is a backend and legal decision, not only a front-end one.
- Transport news sub-types (about a hundred terms from the taxonomy), road-safety figure names and units.
- Place names and province names.
- The newsroom (login and dashboard), which is not part of the public site.
