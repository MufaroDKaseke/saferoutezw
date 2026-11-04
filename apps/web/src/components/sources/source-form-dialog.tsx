"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SelectField } from "@/components/shared/filters";
import { createSource, updateSource } from "@/lib/api/sources";
import { ValidationError, errorMessage } from "@/lib/api/errors";
import type { SourceInput } from "@/lib/api/types";
import { TIER_LABEL } from "@/lib/formatters/labels";
import type { SourceSummary, VerificationTier } from "@/types";

const INTERVALS = [
  { value: "180", label: "Every 3 minutes (default)" },
  { value: "300", label: "Every 5 minutes" },
  { value: "900", label: "Every 15 minutes" },
  { value: "3600", label: "Every hour" },
] as const;

const TIERS = (Object.keys(TIER_LABEL) as VerificationTier[]).map((value) => ({ value, label: TIER_LABEL[value] }));

interface Draft {
  name: string;
  feedUrl: string;
  interval: string;
  tier: VerificationTier;
  rights: string;
}

function toDraft(source: SourceSummary | null): Draft {
  return {
    name: source?.name ?? "",
    feedUrl: source?.feedUrl ?? "",
    interval: String(source?.pollIntervalSeconds ?? 180),
    tier: source?.verificationTier ?? "unverified",
    rights: source?.rightsNotes ?? "",
  };
}

/**
 * Add or edit an RSS feed. Only RSS can be added today; the source model already
 * carries a `kind`, so WhatsApp, social and official channels can join later.
 */
export function SourceFormDialog({
  open,
  onOpenChange,
  source,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Null to add a new feed. */
  source: SourceSummary | null;
}) {
  // Remount the form whenever the dialog opens for a different source.
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open ? <FormBody key={source?.id ?? "new"} source={source} onClose={() => onOpenChange(false)} /> : null}
    </Dialog>
  );
}

function FormBody({ source, onClose }: { source: SourceSummary | null; onClose: () => void }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(source));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<{ field: string | null; message: string } | null>(null);
  const editing = !!source;

  const fieldError = (field: string) => (error?.field === field ? error.message : null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    const input: SourceInput = {
      name: draft.name,
      feedUrl: draft.feedUrl,
      pollIntervalSeconds: Number(draft.interval),
      verificationTier: draft.tier,
      rightsNotes: draft.rights,
    };
    try {
      const result = source ? await updateSource(source.id, input) : await createSource(input);
      toast.success(result.message);
      onClose();
    } catch (e) {
      if (e instanceof ValidationError) setError({ field: e.field, message: e.message });
      else setError({ field: null, message: errorMessage(e) });
    } finally {
      setPending(false);
    }
  };

  return (
    <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
      <form onSubmit={submit} className="space-y-5" noValidate>
        <DialogHeader>
          <DialogTitle className="text-lg font-bold">{editing ? `Edit ${source.name}` : "Add an RSS feed"}</DialogTitle>
          <DialogDescription>
            Articles from this feed are screened for road-safety keywords. Nothing is published automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="src-name">Publisher name</Label>
          <Input
            id="src-name"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            aria-invalid={!!fieldError("name")}
            aria-describedby={fieldError("name") ? "src-name-err" : undefined}
            autoComplete="off"
          />
          {fieldError("name") ? (
            <p id="src-name-err" role="alert" className="text-xs font-medium text-red-700">
              {fieldError("name")}
            </p>
          ) : null}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="src-url">Feed URL</Label>
          <Input
            id="src-url"
            type="url"
            inputMode="url"
            placeholder="https://example.com/feed"
            value={draft.feedUrl}
            onChange={(e) => setDraft({ ...draft, feedUrl: e.target.value })}
            aria-invalid={!!fieldError("feedUrl")}
            aria-describedby={fieldError("feedUrl") ? "src-url-err" : undefined}
            autoComplete="off"
          />
          {fieldError("feedUrl") ? (
            <p id="src-url-err" role="alert" className="text-xs font-medium text-red-700">
              {fieldError("feedUrl")}
            </p>
          ) : null}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField
            label="Polling"
            value={draft.interval}
            onChange={(v) => setDraft({ ...draft, interval: v ?? "180" })}
            options={INTERVALS}
            allLabel="Every 3 minutes (default)"
          />
          <SelectField
            label="Verification tier"
            value={draft.tier}
            onChange={(v) => setDraft({ ...draft, tier: v ?? "unverified" })}
            options={TIERS}
            allLabel="Unverified"
          />
        </div>
        {fieldError("pollIntervalSeconds") ? (
          <p role="alert" className="text-xs font-medium text-red-700">
            {fieldError("pollIntervalSeconds")}
          </p>
        ) : null}

        <div className="space-y-1.5">
          <Label htmlFor="src-rights">Reuse and licensing notes (optional)</Label>
          <Textarea id="src-rights" value={draft.rights} onChange={(e) => setDraft({ ...draft, rights: e.target.value })} rows={3} />
        </div>

        <p className="text-xs text-slate-600">Source type: RSS feed. WhatsApp, social and official sources are planned and cannot be added yet.</p>

        {error && !error.field ? (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
            {error.message}
          </p>
        ) : null}

        <DialogFooter>
          <Button type="button" variant="outline" size="lg" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" size="lg" disabled={pending}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {editing ? "Save changes" : "Add feed"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
