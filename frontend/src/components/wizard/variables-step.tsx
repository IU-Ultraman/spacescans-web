"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { VariableCoveragePanel } from "./variable-coverage-panel";

interface VariablesStepProps {
  taskId: string;
  onComplete: (selectedVariables: string[]) => void;
  onBack: () => void;
  initialSelection?: string[];
}

const V1_VARIABLES = [
  {
    id: "ndi",
    label: "Neighborhood Deprivation Index (NDI)",
    description:
      "Singh's composite Block Group deprivation index, 2012–2022.",
  },
  {
    id: "walkability",
    label: "EPA Walkability Index",
    description:
      "EPA's national walkability index per Block Group, 2016–2021.",
  },
] as const;

export function VariablesStep({
  taskId,
  onComplete,
  onBack,
  initialSelection = [],
}: VariablesStepProps) {
  const [selected, setSelected] = useState<string[]>(initialSelection);

  const toggle = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id]
    );
  };

  const canContinue = selected.length >= 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">
          Experiment: BG NDI + Walkability (v1)
        </CardTitle>
        <CardDescription>
          Select one or both variables to compute for your cohort. More
          variables will be added in future versions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {V1_VARIABLES.map((v) => (
          <label
            key={v.id}
            className="flex items-start gap-3 rounded-md border border-border p-3 hover:bg-muted/30 cursor-pointer"
          >
            <Checkbox
              checked={selected.includes(v.id)}
              onCheckedChange={() => toggle(v.id)}
              className="mt-0.5"
            />
            <div className="flex-1">
              <div className="font-medium">{v.label}</div>
              <div className="text-sm text-muted-foreground">
                {v.description}
              </div>
              {selected.includes(v.id) && (
                <VariableCoveragePanel taskId={taskId} variableKey={v.id} />
              )}
            </div>
          </label>
        ))}

        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack} size="lg">
            <ArrowLeft className="size-4" />
            Back
          </Button>
          <Button
            onClick={() => onComplete(selected)}
            disabled={!canContinue}
            size="lg"
          >
            Next
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
