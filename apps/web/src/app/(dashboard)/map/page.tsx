import type { Metadata } from "next";
import { MapView } from "@/components/maps/map-view";

export const metadata: Metadata = { title: "Safety Map" };

export default function MapPage() {
  return <MapView />;
}
