"use client";

import { Loader2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";

/** The one line that says what sharing means; shown wherever it can be set. */
export const SHARE_EXPLANATION =
  "Everyone who signs in to this deployment can then find and select it; only you can edit, unshare or delete it. Share only if the data's terms allow it.";

export function ShareToggle({
  checked,
  onChange,
  disabled = false,
  busy = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  busy?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5">
      <Checkbox
        checked={checked}
        disabled={disabled || busy}
        onCheckedChange={(next) => onChange(next === true)}
        className="mt-0.5"
      />
      <span className="space-y-0.5">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          Share with all users of this deployment
          {busy && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
        </span>
        <span className="block text-xs text-muted-foreground">{SHARE_EXPLANATION}</span>
      </span>
    </label>
  );
}
