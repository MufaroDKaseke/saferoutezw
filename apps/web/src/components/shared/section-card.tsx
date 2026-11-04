import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** A titled card: 16px / 700 title, optional description and right-hand action. */
export function SectionCard({
  title,
  description,
  icon,
  action,
  children,
  className,
  bodyClassName,
  as: Heading = "h2",
  id,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  as?: "h2" | "h3";
  id?: string;
}) {
  return (
    <Card className={cn("min-w-0", className)} id={id}>
      <div className="flex flex-wrap items-start justify-between gap-3 px-(--card-spacing)">
        <div className="min-w-0">
          <Heading className="flex items-center gap-2 text-base leading-snug font-bold text-foreground">
            {icon}
            {title}
          </Heading>
          {description ? <p className="mt-0.5 text-xs text-slate-600">{description}</p> : null}
        </div>
        {action ? <div className="shrink-0 text-sm">{action}</div> : null}
      </div>
      {children !== undefined ? <div className={cn("min-w-0 px-(--card-spacing)", bodyClassName)}>{children}</div> : null}
    </Card>
  );
}
