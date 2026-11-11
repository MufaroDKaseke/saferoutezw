import type { Metadata, Viewport } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SCOPE_NAME } from "@/lib/scope";
import "./globals.css";

// The concept design guide specifies Inter for the interface. Geist Mono is kept
// for references and identifiers (SR-0412, EV-WA-…), where fixed width helps.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "SafeRouteZW · Road safety intelligence",
    template: "%s · SafeRouteZW",
  },
  description:
    `AI-assisted road safety intelligence for ${SCOPE_NAME}, with mandatory human editorial approval before anything is shared.`,
};

export const viewport: Viewport = {
  themeColor: "#0f172a",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* Browser extensions (e.g. ColorZilla's cz-shortcut-listen) add attributes to <body> before React loads. */}
      <body className="min-h-full bg-background text-foreground" suppressHydrationWarning>
        <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
        <Toaster theme="light" position="bottom-right" />
      </body>
    </html>
  );
}
