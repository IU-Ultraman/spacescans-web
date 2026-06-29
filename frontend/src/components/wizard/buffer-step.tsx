"use client";

import { useState } from "react";
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
import { ArrowLeft, ArrowRight } from "lucide-react";

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
}

export function BufferStep({ onComplete, onBack, initialConfig }: BufferStepProps) {
  const [size, setSize] = useState<string>(
    initialConfig?.size?.toString() ?? "270"
  );
  const [rasterResM, setRasterResM] = useState<number>(
    initialConfig?.raster_res_m ?? 25
  );

  const sizeNum = parseFloat(size);
  const isValid = !isNaN(sizeNum) && sizeNum > 0 && sizeNum <= 100000;

  const handleNext = () => {
    if (isValid) {
      onComplete({ size: sizeNum, raster_res_m: rasterResM });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Exposure Area (Buffer)</CardTitle>
        <CardDescription>
          Choose how large an area around each home to summarize exposures over.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <p className="text-xs text-muted-foreground">
          For each person&apos;s home, we draw a circle of the radius you set and
          summarize the surrounding environment inside it — so each exposure
          reflects the area around the address, not just the single point.
          Set the circle&apos;s radius and how finely it&apos;s measured below.
        </p>

        {/* Size input */}
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
          {size && !isValid && (
            <p className="text-xs text-destructive">
              Enter a value between 1 and 100,000 meters.
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            Typical: 270 m (about a 3–5 minute walk). A larger circle captures a
            wider area around the home but takes significantly longer to run.
          </p>
        </div>

        {/* Rasterization resolution */}
        <div className="space-y-2">
          <Label htmlFor="raster-res">Measurement grid size (m)</Label>
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
            How finely the circle is gridded when overlapping it with map data —
            smaller squares = more precise, slower. 25 m is the standard and
            works well for most studies.
          </p>
        </div>

        {/* Navigation */}
        <div className="flex justify-between pt-2">
          <Button variant="outline" onClick={onBack} size="lg">
            <ArrowLeft className="size-4" />
            Back
          </Button>
          <Button onClick={handleNext} disabled={!isValid} size="lg">
            Next
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
