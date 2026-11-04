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
import type { IncidentDetail, LocationInfo } from "@/types";

const STATUS_LABEL: Record<LocationInfo["status"], string> = {
  unresolved: "Unresolved",
  ambiguous: "Ambiguous",
  resolved: "Proposed (not confirmed)",
  editor_confirmed: "Confirmed by an editor",
};

const STATUS_HELP: Record<LocationInfo["status"], string> = {
  unresolved: "No usable position is known. Nothing is shown on the map.",
  ambiguous: "Several places match, or the match is too broad. No marker is shown until an editor picks one.",
  resolved: "A geographic reference proposed this position. It is not shown as confirmed until you accept it.",
  editor_confirmed: "An editor accepted or supplied this position.",
};

/**
 * Editor-only location control (API mode). The server decides whether the action is allowed;
 * this panel only sends it. Candidates come from the geographic reference, never invented.
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
  const [precision, setPrecision] = useState("");
  if (!info) return null;

  const send = async (input: LocationAction, done: string) => {
    setBusy(true);
    try {
      await confirmLocation(incident.id, input);
      toast.success(done);
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
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="location-panel-title" className="flex items-center gap-1.5 text-sm font-bold">
          <MapPin className="size-4" aria-hidden /> Location
        </h3>
        <Chip tone={info.status === "editor_confirmed" ? "emerald" : info.status === "resolved" ? "amber" : "slate"}>
          {STATUS_LABEL[info.status]}
        </Chip>
      </div>
      <p className="text-sm">
        Reported as: <strong>{incident.locationText ?? "no location text"}</strong>
      </p>
      <p className="text-xs text-slate-600">{STATUS_HELP[info.status]}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-slate-600">
        {info.source ? (<><dt>Source</dt><dd className="font-medium text-foreground">{info.source}</dd></>) : null}
        {info.method ? (<><dt>Method</dt><dd className="font-medium text-foreground">{info.method}</dd></>) : null}
        {info.precisionMeters != null ? (<><dt>Precision</dt><dd className="font-medium text-foreground">about {Math.round(info.precisionMeters)} m</dd></>) : null}
        {info.note ? (<><dt>Note</dt><dd className="font-medium text-foreground">{info.note}</dd></>) : null}
      </dl>

      {info.candidates.length > 0 ? (
        <ul className="space-y-1.5" aria-label="Candidate locations">
          {info.candidates.map((c, n) => (
            <li key={`${c.label}-${n}`} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm">
              <span>
                {c.label}
                <span className="block text-xs text-slate-600">
                  {c.latitude.toFixed(4)}, {c.longitude.toFixed(4)}
                  {c.precisionMeters != null ? ` · about ${Math.round(c.precisionMeters)} m` : ""} · {c.source}
                </span>
              </span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!canDecide || busy}
                onClick={() => send({ action: "select_candidate", candidateIndex: n }, "Location confirmed.")}
              >
                Use this location
              </Button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {info.status === "resolved" ? (
          <Button type="button" size="sm" disabled={!canDecide || busy} onClick={() => send({ action: "accept_proposed" }, "Location confirmed.")}>
            Accept proposed location
          </Button>
        ) : null}
        {info.status !== "unresolved" ? (
          <Button type="button" size="sm" variant="outline" disabled={!canDecide || busy} onClick={() => send({ action: "mark_unresolved" }, "Location marked unresolved.")}>
            Mark unresolved
          </Button>
        ) : null}
      </div>

      <details className="text-sm">
        <summary className="cursor-pointer font-medium">Enter coordinates yourself</summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor="loc-lat">Latitude</Label>
            <Input id="loc-lat" inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="-17.8292" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="loc-lng">Longitude</Label>
            <Input id="loc-lng" inputMode="decimal" value={lng} onChange={(e) => setLng(e.target.value)} placeholder="31.0522" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="loc-prec">Precision (m, optional)</Label>
            <Input id="loc-prec" inputMode="numeric" value={precision} onChange={(e) => setPrecision(e.target.value)} placeholder="50" />
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          className="mt-2"
          disabled={!canDecide || busy || !validCoords}
          onClick={() =>
            send(
              {
                action: "set_coordinates",
                latitude: latNum,
                longitude: lngNum,
                precisionMeters: precision.trim() !== "" && Number.isFinite(Number(precision)) ? Number(precision) : undefined,
              },
              "Location confirmed.",
            )
          }
        >
          Confirm these coordinates
        </Button>
      </details>
      {!canDecide ? <p className="text-xs text-slate-600">Only an editor or admin can change the location.</p> : null}
    </div>
  );
}
