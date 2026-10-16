"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";

/** The one line that says what sharing means; shown wherever it can be set. */
export const SHARE_EXPLANATION =
  "Everyone who signs in to this deployment can then find and select it; only you can edit, unshare or delete it.";

/** The warning shown next to every share control (PHASE_D 7.1 item 6). */
export const SHARE_WARNING =
  "Sharing lets every user of this deployment link these values to their own data, and you are responsible for making sure the source's terms allow that.";

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
    <div className="space-y-2">
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
      <p
        role="note"
        className="flex items-start gap-1.5 rounded-md border border-amber-500/20 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-700 dark:text-amber-400"
      >
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
        <span>{SHARE_WARNING}</span>
      </p>
    </div>
  );
}
