"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useDemoSession } from "@/hooks/use-demo-session";

/**
 * Sends the visitor to /login after they chose "Sign out" in this browser.
 * This is a demo convenience, not access control: there is no authentication
 * backend yet and every API call must be authorised by the backend later.
 */
export function SessionGuard() {
  const router = useRouter();
  const { signedOut } = useDemoSession();
  useEffect(() => {
    if (signedOut) router.replace("/login");
  }, [signedOut, router]);
  return null;
}
