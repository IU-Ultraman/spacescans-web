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
        <CardTitle className="text-lg">Buffer Settings</CardTitle>
        <CardDescription>
          Configure the spatial buffer around each data point.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <p className="text-xs text-muted-foreground">
          The spacescans-pipeline computes a circular buffer (radius in meters) around each
          patient&apos;s residence and overlays it with the chosen boundary layer. Set the radius
          and rasterization resolution below.
        </p>

        {/* Size input */}
        <div className="space-y-2">
          <Label htmlFor="buffer-size">Buffer Size</Label>
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
            Typical: 270 m (about a 3-5 minute walk). Larger buffers take significantly longer to run.
          </p>
        </div>

        {/* Rasterization resolution */}
        <div className="space-y-2">
          <Label htmlFor="raster-res">Rasterization resolution (m)</Label>
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
            Resolution for boundary overlap rasterization. Lower = more accurate, slower. 25 m is the standard.
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
