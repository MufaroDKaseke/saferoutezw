import Link from "next/link";
import { BrandMark, Wordmark } from "@/components/layout/brand";

const NAV = [
  { href: "/public/alerts", label: "Alerts" },
  { href: "/public/map", label: "Map" },
  { href: "/public/routes", label: "Plan route" },
  { href: "/public/operators", label: "Operators" },
  { href: "/public/subscribe", label: "Get alerts" },
];

export function SiteHeader() {
  return (
    <header className="border-b border-slate-200 bg-white print:hidden">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-1 px-4 py-2">
        <Link href="/public" className="flex min-h-11 items-center gap-2" aria-label="SafeRouteZW home">
          <BrandMark className="size-8" />
          <Wordmark tone="dark" />
        </Link>
        <nav aria-label="Main" className="flex flex-wrap gap-x-1">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex min-h-11 items-center rounded-md px-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-900"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mt-12 border-t border-slate-200 bg-white py-6 text-sm text-slate-600 print:hidden">
      <div className="mx-auto max-w-5xl space-y-2 px-4">
        <p>
          SafeRouteZW shares road safety notices that a human editor has reviewed and published. It may be incomplete or
          out of date. <strong>No alert on your route does not mean the road is safe.</strong> Follow police and traffic
          authority instructions.
        </p>
        <p>
          <Link className="underline" href="/public/subscription/manage">
            Manage or cancel alerts
          </Link>
        </p>
      </div>
    </footer>
  );
}

export function PageShell({ title, intro, children }: { title: string; intro?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {intro ? <p className="max-w-2xl text-slate-600">{intro}</p> : null}
      </div>
      {children}
    </div>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-semibold">We could not load this information.</p>
      <p>{message}</p>
    </div>
  );
}
