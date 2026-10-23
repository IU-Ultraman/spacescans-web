"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ArrowLeft, ArrowRight, Info, MapPin, Rows3 } from "lucide-react";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import { KIND_INFO, type RegisteredDataset } from "@/lib/datasets";
import {
  DEFAULT_OUTPUT_LEVEL,
  OUTPUT_LEVELS,
  OUTPUT_LEVEL_INFO,
  type OutputLevel,
} from "@/lib/output-level";
import { cn } from "@/lib/utils";

export interface BufferConfig {
  // spacescans only supports circular buffers (shapely .buffer with
  // a resolution count); square/rectangle buffers have no pipeline code path,
  // so we omit the shape field from the wizard entirely.
  size: number;
  raster_res_m: number;
}

interface BufferStepProps {
  onComplete: (config: BufferConfig, outputLevel: OutputLevel) => void;
  onBack: () => void;
  initialConfig?: BufferConfig;
  initialOutputLevel?: OutputLevel;
  /** The catalog variables chosen in the first step — drive which controls apply. */
  selectedVariables: string[];
  /** The user's registered datasets chosen next to them. */
  selectedDatasets?: RegisteredDataset[];
}

/** Step 3, "Settings": the buffer radius (when any selection uses one) and
 *  the output level (always). */
export function BufferStep({
  onComplete,
  onBack,
  initialConfig,
  initialOutputLevel = DEFAULT_OUTPUT_LEVEL,
  selectedVariables,
  selectedDatasets = [],
}: BufferStepProps) {
  const [size, setSize] = useState<string>(
    initialConfig?.size?.toString() ?? "270"
  );
  const [outputLevel, setOutputLevel] = useState<OutputLevel>(initialOutputLevel);
  // Overlap grid resolution is fixed at the 25 m standard — not user-configurable.
  // Still emitted in the config so the backend C3 areal linkage receives it.
  const rasterResM = initialConfig?.raster_res_m ?? 25;

  const { catalog } = useVariableCatalog();

  // Partition the selection by how it links to space:
  //   areal     → buffer ∩ polygons (uses buffer AND the grid resolution)
  //   grid      → buffer ∩ raster cells   (uses buffer, not the grid resolution)
  //   proximity → distance from the point (uses NEITHER — measured at the location)
  // A registered dataset's method follows its kind (features = proximity).
  const { bufferLabels, proximityLabels } = useMemo(() => {
    const buffer: string[] = [];
    const proximity: string[] = [];
    for (const key of selectedVariables) {
      const meta = catalog?.variables[key];
      const label = meta?.label ?? key;
      if ((meta?.spatial_method ?? "areal") === "proximity") proximity.push(label);
      else buffer.push(label);
    }
    for (const d of selectedDatasets) {
      if (KIND_INFO[d.kind]?.method === "proximity") proximity.push(d.name);
      else buffer.push(d.name);
    }
    return { bufferLabels: buffer, proximityLabels: proximity };
  }, [selectedVariables, selectedDatasets, catalog]);

  const list = (labels: string[]) => labels.join(", ");
  const total = selectedVariables.length + selectedDatasets.length;
  const bufferApplies = bufferLabels.length > 0;

  const sizeNum = parseFloat(size);
  const sizeValid = !isNaN(sizeNum) && sizeNum > 0 && sizeNum <= 100000;
  // When no selected exposure uses the buffer (proximity-only), the radius is
  // irrelevant, so the step is always ready to advance.
  const canAdvance = bufferApplies ? sizeValid : true;

  const handleNext = () => {
    if (!canAdvance) return;
    onComplete(
      {
        size: bufferApplies && sizeValid ? sizeNum : 270,
        raster_res_m: rasterResM,
      },
      outputLevel,
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Settings</CardTitle>
        <CardDescription>
          How large an area around each location to summarize exposures over,
          and what one row of the result stands for.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section className="space-y-4">
          <h3 className="text-sm font-semibold">Exposure area (buffer)</h3>
          {bufferApplies ? (
            <>
              <p className="text-xs text-muted-foreground">
                Around each location in your upload we draw a circle of the radius
                you set and summarize the surrounding environment inside it — so
                the exposure reflects the area around the location, not just the
                single point.
              </p>

              {/* Circle radius — applies to areal + grid exposures */}
              <div className="space-y-2">
                <Label htmlFor="buffer-size">Circle radius</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id="buffer-size"
                    type="number"
                    min={1}
                    max={100000}
                    value={size}
                    onChange={(e) => setSize(e.target.value)}
                    className="max-w-[200px]"
                    placeholder="270"
                  />
                  <span className="text-sm text-muted-foreground">meters</span>
                </div>
                {size && !sizeValid && (
                  <p className="text-xs text-destructive">
                    Enter a value between 1 and 100,000 meters.
                  </p>
                )}
                <p className="text-xs text-muted-foreground">
                  Applied to {bufferLabels.length} of your {total} exposures.
                  Typical: 270 m (about a 3–5 minute walk). A larger circle
                  captures a wider area but takes longer to run.
                </p>
              </div>
            </>
          ) : (
            <div className="flex items-start gap-3 rounded-lg border bg-muted/40 p-4">
              <MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <div className="space-y-1 text-sm">
                <p className="font-medium text-foreground">
                  No buffer needed for your selection
                </p>
                <p className="text-xs text-muted-foreground">
                  {list(proximityLabels)} {proximityLabels.length === 1 ? "is" : "are"}{" "}
                  measured as the straight-line distance from the exact location
                  to the nearest feature — there&apos;s no surrounding area to
                  summarize, so the circle radius doesn&apos;t apply.
                </p>
              </div>
            </div>
          )}

          {/* Proximity callout — shown whenever proximity exposures are mixed in */}
          {bufferApplies && proximityLabels.length > 0 && (
            <div className="flex items-start gap-2.5 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3">
              <Info className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
              <p className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">
                  {list(proximityLabels)}
                </span>{" "}
                {proximityLabels.length === 1 ? "is" : "are"} measured at the exact
                location (distance to the nearest feature) and{" "}
                <span className="font-medium">ignore the radius</span>.
              </p>
            </div>
          )}
        </section>

        {/* Output level — participant by default */}
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Rows3 className="size-4 text-muted-foreground" /> Output
          </h3>
          <div role="radiogroup" aria-label="Output level" className="grid gap-2 sm:grid-cols-2">
            {OUTPUT_LEVELS.map((level) => {
              const info = OUTPUT_LEVEL_INFO[level];
              const checked = outputLevel === level;
              return (
                <button
                  key={level}
                  type="button"
                  role="radio"
                  aria-checked={checked}
                  onClick={() => setOutputLevel(level)}
                  className={cn(
                    "rounded-lg border p-3 text-left transition-colors",
                    checked
                      ? "border-primary bg-primary/10"
                      : "hover:bg-muted/60",
                  )}
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <span
                      className={cn(
                        "inline-block size-3.5 shrink-0 rounded-full border",
                        checked ? "border-[5px] border-primary" : "border-muted-foreground/50",
                      )}
                    />
                    {info.label}
                    {level === DEFAULT_OUTPUT_LEVEL && (
                      <span className="text-xs font-normal text-muted-foreground">(default)</span>
                    )}
                  </span>
                  <span className="mt-1 block pl-[1.375rem] text-xs text-muted-foreground">
                    {info.explain}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {/* Navigation */}
        <div className="flex justify-between pt-2">
          <Button variant="outline" onClick={onBack} size="lg">
            <ArrowLeft className="size-4" />
            Back
          </Button>
          <Button onClick={handleNext} disabled={!canAdvance} size="lg">
            Next
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
