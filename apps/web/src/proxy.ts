import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { isRouteAllowed, parseAppMode } from "@/lib/app-mode";

/**
 * NUST FM mode: the road-safety pages are not just hidden from the menu, they do not exist.
 * A direct URL such as /map or /public/routes is answered with the normal "not found" page.
 * In road-safety mode every request passes straight through.
 */
export function proxy(request: NextRequest) {
  const mode = parseAppMode(process.env.NEXT_PUBLIC_APP_MODE);
  if (isRouteAllowed(request.nextUrl.pathname, mode)) return NextResponse.next();
  return NextResponse.rewrite(new URL("/not-found-in-this-mode", request.url));
}

// Only the road-safety sections need checking; everything else is never touched by the proxy.
export const config = {
  matcher: [
    "/map/:path*",
    "/incidents/:path*",
    "/blackspots/:path*",
    "/alerts/:path*",
    "/reviews/:path*",
    "/intelligence/:path*",
    "/public/:path*",
  ],
};
