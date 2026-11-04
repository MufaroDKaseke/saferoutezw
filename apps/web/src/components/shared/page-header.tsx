import { cn } from "@/lib/utils";

/** Page title block: 30px / 700 title, one short line, optional actions on the right. */
export function PageHeader({
  title,
  description,
  actions,
  meta,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  /** Small line above the title, such as a reference and status chips. */
  meta?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-x-6 gap-y-3", className)}>
      <div className="min-w-0 max-w-3xl">
        {meta ? <div className="mb-2 flex flex-wrap items-center gap-2">{meta}</div> : null}
        <h1 className="text-balance text-[1.625rem] leading-tight font-bold tracking-tight text-foreground sm:text-[1.875rem]">
          {title}
        </h1>
        {description ? <p className="mt-1 max-w-prose text-[13px] leading-snug text-slate-600">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
