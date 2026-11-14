import type { Metadata } from "next";
import { BulletinList } from "@/components/newsroom/bulletin-list";

export const metadata: Metadata = { title: "Bulletins" };

// NUST FM only: the proxy answers "not found" for this route in road-safety mode.
export default function BulletinsPage() {
  return <BulletinList />;
}
