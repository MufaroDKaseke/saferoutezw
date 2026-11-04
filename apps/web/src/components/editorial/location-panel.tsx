"use client";

import { useState } from "react";
import { MapPin } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Chip } from "@/components/shared/status";
import { errorMessage } from "@/lib/api/errors";
import { confirmLocation, type LocationAction } from "@/lib/api/reviews";
import type { IncidentDetail } from "@/types";

/**
 * Editor-only location control (API mode): pick one of the suggested places, or type coordinates.
 * The server decides whether the action is allowed; suggestions come from the geocoder, never invented.
 */
export function LocationPanel({
  incident,
  canDecide,
  onChanged,
}: {
  incident: IncidentDetail;
  canDecide: boolean;
  onChanged: () => void;
}) {
  const info = incident.locationInfo;
  const [busy, setBusy] = useState(false);
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  if (!info) return null;

  const send = async (input: LocationAction) => {
    setBusy(true);
    try {
      await confirmLocation(incident.id, input);
      toast.success("Location saved.");
      onChanged();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const latNum = Number(lat);
  const lngNum = Number(lng);
  const validCoords = lat.trim() !== "" && lng.trim() !== "" && Number.isFinite(latNum) && Number.isFinite(lngNum);

  return (
    <div className="space-y-3 rounded-lg border border-slate-300 p-4" aria-labelledby="location-panel-title">
      <div className="flex items-center justify-between gap-2">
        <h3 id="location-panel-title" className="flex items-center gap-1.5 text-sm font-bold">
          <MapPin className="size-4" aria-hidden /> Location
        </h3>
        {info.status === "editor_confirmed" ? <Chip tone="emerald">Confirmed</Chip> : null}
      </div>
      <p className="text-sm">
        Reported as: <strong>{incident.locationText ?? "no location text"}</strong>
      </p>

      {info.candidates.length > 0 ? (
        <ul className="space-y-1.5" aria-label="Suggested locations">
          {info.candidates.map((c, n) => (
            <li key={`${c.label}-${n}`} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm">
              <span>{c.label}</span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!canDecide || busy}
                onClick={() => send({ action: "select_candidate", candidateIndex: n })}
              >
                Use this location
              </Button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="grid items-end gap-2 sm:grid-cols-[1fr_1fr_auto]">
        <div className="space-y-1">
          <Label htmlFor="loc-lat">Latitude</Label>
          <Input id="loc-lat" inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="-17.8292" disabled={!canDecide} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="loc-lng">Longitude</Label>
          <Input id="loc-lng" inputMode="decimal" value={lng} onChange={(e) => setLng(e.target.value)} placeholder="31.0522" disabled={!canDecide} />
        </div>
        <Button
          type="button"
          disabled={!canDecide || busy || !validCoords}
          onClick={() => send({ action: "set_coordinates", latitude: latNum, longitude: lngNum })}
        >
          Use coordinates
        </Button>
      </div>
      {!canDecide ? <p className="text-xs text-slate-600">Only an editor or admin can change the location.</p> : null}
    </div>
  );
}
