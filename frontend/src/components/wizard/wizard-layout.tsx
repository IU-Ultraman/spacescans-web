"use client";

import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

const STEPS = [
  { label: "Upload Data", description: "CSV file" },
  { label: "Buffer Settings", description: "Shape & size" },
  { label: "Variables", description: "Ontology selection" },
  { label: "Review & Run", description: "Confirm & start" },
];

interface WizardLayoutProps {
  currentStep: number;
  children: React.ReactNode;
}

export function WizardLayout({ currentStep, children }: WizardLayoutProps) {
  return (
    <div className="mx-auto max-w-4xl">
      {/* Stepper */}
      <nav aria-label="Wizard steps" className="mb-8">
        <ol className="flex items-center">
          {STEPS.map((step, index) => {
            const isCompleted = index < currentStep;
            const isCurrent = index === currentStep;
            const isLast = index === STEPS.length - 1;

            return (
              <li
                key={step.label}
                className={cn("flex items-center", !isLast && "flex-1")}
              >
                {/* Step indicator */}
                <div className="flex flex-col items-center gap-1.5">
                  <div
                    className={cn(
                      "flex size-9 items-center justify-center rounded-full border-2 text-sm font-semibold transition-all duration-300",
                      isCompleted &&
                        "border-primary bg-primary text-primary-foreground",
                      isCurrent &&
                        "border-primary bg-primary/10 text-primary ring-4 ring-primary/20",
                      !isCompleted &&
                        !isCurrent &&
                        "border-muted-foreground/30 text-muted-foreground/50"
                    )}
                  >
                    {isCompleted ? (
                      <Check className="size-4" strokeWidth={3} />
                    ) : (
                      index + 1
                    )}
                  </div>
                  <div className="flex flex-col items-center">
                    <span
                      className={cn(
                        "text-xs font-medium transition-colors",
                        isCurrent && "text-foreground",
                        isCompleted && "text-primary",
                        !isCurrent &&
                          !isCompleted &&
                          "text-muted-foreground/60"
                      )}
                    >
                      {step.label}
                    </span>
                    <span className="text-[10px] text-muted-foreground/50">
                      {step.description}
                    </span>
                  </div>
                </div>

                {/* Connector line */}
                {!isLast && (
                  <div className="mx-3 mb-6 h-0.5 flex-1">
                    <div
                      className={cn(
                        "h-full rounded-full transition-colors duration-500",
                        isCompleted ? "bg-primary" : "bg-muted-foreground/20"
                      )}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Step content */}
      <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
        {children}
      </div>
    </div>
  );
}
