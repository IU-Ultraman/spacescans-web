"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { OntologyTree } from "@/components/ontology-tree";
import { OntologySearch } from "@/components/ontology-search";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowLeft, ArrowRight, X } from "lucide-react";

interface VariablesStepProps {
  onComplete: (selectedVariables: string[]) => void;
  onBack: () => void;
  initialSelection?: string[];
}

export function VariablesStep({
  onComplete,
  onBack,
  initialSelection = [],
}: VariablesStepProps) {
  const [selected, setSelected] = useState<string[]>(initialSelection);
  const [metadata, setMetadata] = useState<
    Record<string, { id: string; label: string; definition: string }>
  >({});

  useEffect(() => {
    fetch("/ontology/metadata.json")
      .then((r) => r.json())
      .then(setMetadata)
      .catch(() => {});
  }, []);

  const handleSelectionChange = useCallback((ids: string[]) => {
    setSelected(ids);
  }, []);

  const handleSearchSelect = useCallback(
    (id: string) => {
      if (!selected.includes(id)) {
        setSelected((prev) => [...prev, id]);
      }
    },
    [selected]
  );

  const handleRemove = useCallback((id: string) => {
    setSelected((prev) => prev.filter((s) => s !== id));
  }, []);

  const handleNext = () => {
    if (selected.length > 0) {
      onComplete(selected);
    }
  };

  const getLabel = (id: string) => {
    const meta = metadata[id];
    return meta ? meta.label.replace(/_/g, " ") : id;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Select Variables</CardTitle>
        <CardDescription>
          Browse the ontology tree or search to find variables for your analysis.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
          {/* Left: search + tree */}
          <div className="space-y-3">
            <OntologySearch onSelect={handleSearchSelect} />
            <div className="rounded-lg border border-border">
              <ScrollArea className="h-[400px]">
                <div className="p-2">
                  <OntologyTree
                    selectable
                    selected={selected}
                    onSelectionChange={handleSelectionChange}
                  />
                </div>
              </ScrollArea>
            </div>
          </div>

          {/* Right: selected variables */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-foreground">
                Selected Variables
              </p>
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                {selected.length}
              </span>
            </div>
            <div className="rounded-lg border border-border">
              <ScrollArea className="h-[400px]">
                {selected.length === 0 ? (
                  <div className="flex h-full items-center justify-center p-8 text-center">
                    <p className="text-sm text-muted-foreground/60">
                      No variables selected yet. Browse the tree or use search
                      to add variables.
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-1.5 p-3">
                    {selected.map((id) => (
                      <span
                        key={id}
                        className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/15"
                      >
                        {getLabel(id)}
                        <button
                          type="button"
                          onClick={() => handleRemove(id)}
                          className="rounded-sm p-0.5 hover:bg-primary/20"
                        >
                          <X className="size-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <div className="flex justify-between pt-2">
          <Button variant="outline" onClick={onBack} size="lg">
            <ArrowLeft className="size-4" />
            Back
          </Button>
          <Button
            onClick={handleNext}
            disabled={selected.length === 0}
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
