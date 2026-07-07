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
import { ArrowLeft, ArrowRight, Info, MapPin } from "lucide-react";
import { useVariableCatalog } from "@/lib/use-variable-catalog";

export interface BufferConfig {
  // spacescans-pipeline only supports circular buffers (shapely .buffer with
  // a resolution count); square/rectangle buffers have no pipeline code path,
  // so we omit the shape field from the wizard entirely.
  size: number;
  raster_res_m: number;
}

interface BufferStepProps {
  onComplete: (config: BufferConfig) => void;
  onBack: () => void;
  initialConfig?: BufferConfig;
  /** The variables chosen in the previous step — drives which controls apply. */
  selectedVariables: string[];
}

export function BufferStep({
  onComplete,
  onBack,
  initialConfig,
  selectedVariables,
}: BufferStepProps) {
  const [size, setSize] = useState<string>(
    initialConfig?.size?.toString() ?? "270"
  );
  const [rasterResM, setRasterResM] = useState<number>(
    initialConfig?.raster_res_m ?? 25
  );

  const { catalog } = useVariableCatalog();

  // Partition the selected variables by how their C3 links to space:
  //   areal     → buffer ∩ Census polygon (uses buffer AND the grid resolution)
  //   grid      → buffer ∩ raster cells   (uses buffer, not the grid resolution)
  //   proximity → distance from the point (uses NEITHER — measured at the address)
  const { areal, grid, proximity } = useMemo(() => {
    const a: string[] = [];
    const g: string[] = [];
    const p: string[] = [];
    for (const key of selectedVariables) {
      const method = catalog?.variables[key]?.spatial_method ?? "areal";
      if (method === "proximity") p.push(key);
      else if (method === "grid") g.push(key);
      else a.push(key);
    }
    return { areal: a, grid: g, proximity: p };
  }, [selectedVariables, catalog]);

  const labelOf = (key: string) => catalog?.variables[key]?.label ?? key;
  const list = (keys: string[]) => keys.map(labelOf).join(", ");

  const bufferVars = [...areal, ...grid];
  const bufferApplies = bufferVars.length > 0;
  const rasterApplies = areal.length > 0;

  const sizeNum = parseFloat(size);
  const sizeValid = !isNaN(sizeNum) && sizeNum > 0 && sizeNum <= 100000;
  // When no selected exposure uses the buffer (proximity-only), the radius is
  // irrelevant, so the step is always ready to advance.
  const canAdvance = bufferApplies ? sizeValid : true;

  const handleNext = () => {
    if (!canAdvance) return;
    onComplete({
      size: bufferApplies && sizeValid ? sizeNum : 270,
      raster_res_m: rasterResM,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Exposure Area (Buffer)</CardTitle>
        <CardDescription>
          How large an area around each home to summarize exposures over.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {bufferApplies ? (
          <>
            <p className="text-xs text-muted-foreground">
              For each person&apos;s home, we draw a circle of the radius you set
              and summarize the surrounding environment inside it — so the
              exposure reflects the area around the address, not just the single
              point.
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
                Applied to {bufferVars.length} of your{" "}
                {selectedVariables.length} exposures. Typical: 270 m (about a
                3–5 minute walk). A larger circle captures a wider area but takes
                longer to run.
              </p>
            </div>

            {/* Rasterization resolution — areal exposures only */}
            {rasterApplies && (
              <div className="space-y-2">
                <Label htmlFor="raster-res">Overlap grid size (m)</Label>
                <Input
                  id="raster-res"
                  type="number"
                  min={5}
                  max={100}
                  step={5}
                  value={rasterResM}
                  onChange={(e) => setRasterResM(parseInt(e.target.value) || 25)}
                  className="w-32"
                />
                <p className="text-xs text-muted-foreground">
                  How finely each Census area is gridded to measure its overlap
                  with the circle — smaller cells = more precise, slower (25 m is
                  the standard). Used only by area-based exposures ({list(areal)});
                  it grids the Census polygons for the overlap, not the exposure
                  data — the raster exposures (noise, lights, UV) don&apos;t use it.
                </p>
              </div>
            )}
          </>
        ) : (
          <div className="flex items-start gap-3 rounded-lg border bg-muted/40 p-4">
            <MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <div className="space-y-1 text-sm">
              <p className="font-medium text-foreground">
                No buffer needed for your selection
              </p>
              <p className="text-xs text-muted-foreground">
                {list(proximity)} {proximity.length === 1 ? "is" : "are"}{" "}
                measured as the straight-line distance from the exact home
                address to the nearest feature — there&apos;s no surrounding area
                to summarize, so the circle radius doesn&apos;t apply. Continue
                to review.
              </p>
            </div>
          </div>
        )}

        {/* Proximity callout — shown whenever proximity vars are mixed in */}
        {bufferApplies && proximity.length > 0 && (
          <div className="flex items-start gap-2.5 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3">
            <Info className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">
                {list(proximity)}
              </span>{" "}
              {proximity.length === 1 ? "is" : "are"} measured at the exact
              address (distance to the nearest feature) and{" "}
              <span className="font-medium">ignore the radius</span>.
            </p>
          </div>
        )}

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
