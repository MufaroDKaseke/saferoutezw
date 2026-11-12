import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { isRouteAllowed, parseAppMode } from "@/lib/app-mode";

/**
 * Each product serves only its own pages. In NUST FM mode the road-safety pages are not just hidden from the
 * menu, they do not exist: a direct URL such as /map or /public/routes is answered with the normal "not found"
 * page. Likewise the newsroom's story-to-air pages (/stories, /bulletins, /studio, /archive) do not exist in
 * road-safety mode. Every other request passes straight through.
 */
export function proxy(request: NextRequest) {
  const mode = parseAppMode(process.env.NEXT_PUBLIC_APP_MODE);
  if (isRouteAllowed(request.nextUrl.pathname, mode)) return NextResponse.next();
  return NextResponse.rewrite(new URL("/not-found-in-this-mode", request.url));
}

// Only the road-safety and newsroom sections need checking; everything else is never touched by the proxy.
export const config = {
  matcher: [
    "/stories/:path*",
    "/bulletins/:path*",
    "/studio/:path*",
    "/archive/:path*",
    "/map/:path*",
    "/incidents/:path*",
    "/blackspots/:path*",
    "/alerts/:path*",
    "/reviews/:path*",
    "/intelligence/:path*",
    "/public/:path*",
  ],
};
