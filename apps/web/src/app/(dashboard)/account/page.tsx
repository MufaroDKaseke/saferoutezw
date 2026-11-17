import type { Metadata } from "next";
import { AccountView } from "@/components/auth/account-view";

export const metadata: Metadata = { title: "Your account" };

export default function AccountPage() {
  return <AccountView />;
}
