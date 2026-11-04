import * as React from "react"

const MOBILE_BREAKPOINT = 768
const MOBILE_QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

function subscribe(onChange: () => void) {
  const mediaQuery = window.matchMedia(MOBILE_QUERY)
  mediaQuery.addEventListener("change", onChange)
  return () => mediaQuery.removeEventListener("change", onChange)
}

function getSnapshot() {
  return window.matchMedia(MOBILE_QUERY).matches
}

function getServerSnapshot() {
  return false
}

const subscribeNever = () => () => {}

/**
 * Whether the viewport is phone-sized. The first client render always reports
 * `false`, exactly like the server, so the desktop sidebar HTML hydrates cleanly.
 * It flips to the real value right after hydration (Cache Components streams the
 * sidebar behind Suspense, which otherwise lets the client render a different tree).
 */
export function useIsMobile() {
  const hydrated = React.useSyncExternalStore(
    subscribeNever,
    () => true,
    () => false
  )
  const mobile = React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  return hydrated && mobile
}
