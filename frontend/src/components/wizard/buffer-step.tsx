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
import { cn } from "@/lib/utils";
import { ArrowLeft, ArrowRight, Circle, Square } from "lucide-react";

export interface BufferConfig {
  shape: "circle" | "square";
  size: number;
  raster_res_m: number;
}

interface BufferStepProps {
  onComplete: (config: BufferConfig) => void;
  onBack: () => void;
  initialConfig?: BufferConfig;
}

export function BufferStep({ onComplete, onBack, initialConfig }: BufferStepProps) {
  const [shape, setShape] = useState<"circle" | "square">(
    initialConfig?.shape ?? "circle"
  );
  const [size, setSize] = useState<string>(
    initialConfig?.size?.toString() ?? "1000"
  );
  const [rasterResM, setRasterResM] = useState<number>(
    initialConfig?.raster_res_m ?? 25
  );

  const sizeNum = parseFloat(size);
  const isValid = !isNaN(sizeNum) && sizeNum > 0 && sizeNum <= 100000;

  const handleNext = () => {
    if (isValid) {
      onComplete({ shape, size: sizeNum, raster_res_m: rasterResM });
    }
  };

  // Calculate preview dimensions — max 120px side
  const previewSize = Math.min(120, Math.max(40, (sizeNum / 5000) * 120));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Buffer Settings</CardTitle>
        <CardDescription>
          Configure the spatial buffer around each data point.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Shape selection */}
        <div className="space-y-2">
          <Label>Buffer Shape</Label>
          <p className="text-xs text-muted-foreground mb-2">
            v1 supports circular buffers only. Square will be added when the spacescans-pipeline supports it.
          </p>
          <div className="flex gap-3">
            {(["circle", "square"] as const).map((s) => {
              const isCircle = s === "circle";
              const isDisabled = !isCircle;
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    if (!isDisabled) setShape(s);
                  }}
                  disabled={isDisabled}
                  title={isDisabled ? "Not supported by spacescans-pipeline yet" : undefined}
                  className={cn(
                    "flex flex-1 items-center justify-center gap-2.5 rounded-xl border-2 px-4 py-3.5 text-sm font-medium transition-all",
                    shape === s
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-muted-foreground/20 text-muted-foreground hover:border-muted-foreground/40 hover:bg-muted/30",
                    isDisabled && "cursor-not-allowed opacity-50 hover:border-muted-foreground/20 hover:bg-transparent"
                  )}
                >
                  {isCircle ? (
                    <Circle
                      className={cn(
                        "size-5",
                        shape === s && "fill-primary/20"
                      )}
                    />
                  ) : (
                    <Square
                      className={cn(
                        "size-5",
                        shape === s && "fill-primary/20"
                      )}
                    />
                  )}
                  <span className="capitalize">{s}</span>
                </button>
              );
            })}
          </div>
        </div>

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
              placeholder="1000"
            />
            <span className="text-sm text-muted-foreground">meters</span>
          </div>
          {size && !isValid && (
            <p className="text-xs text-destructive">
              Enter a value between 1 and 100,000 meters.
            </p>
          )}
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

        {/* Visual preview */}
        <div className="space-y-2">
          <Label>Preview</Label>
          <div className="flex flex-col items-center justify-center rounded-xl border border-muted-foreground/15 bg-muted/20 p-8">
            <div className="relative flex items-center justify-center">
              {/* Buffer shape */}
              <div
                className={cn(
                  "flex items-center justify-center border-2 border-primary/60 bg-primary/10 transition-all duration-300",
                  shape === "circle" ? "rounded-full" : "rounded-lg"
                )}
                style={{
                  width: `${previewSize}px`,
                  height: `${previewSize}px`,
                }}
              >
                {/* Center point */}
                <div className="size-2.5 rounded-full bg-primary" />
              </div>
            </div>
            <p className="mt-4 text-sm text-muted-foreground">
              {isValid ? `${sizeNum.toLocaleString()} m` : "---"}{" "}
              {shape === "circle" ? "radius" : "side length"}
            </p>
          </div>
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
