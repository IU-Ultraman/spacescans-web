"use client";

import { Component, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

interface Props {
  /** Human label for the card that failed, e.g. "Exposure Histograms". */
  label: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Wraps a single results-page visualization card. If the chart/map throws
 * during render, we show the error message inline instead of blanking the
 * whole results page — and surface the exact message so it's diagnosable.
 */
export class VizErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // Also log to console for devtools inspection.
    // eslint-disable-next-line no-console
    console.error(`[viz] ${this.props.label} failed to render:`, error);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4 text-sm">
          <div className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-400">
            <AlertTriangle className="size-4" />
            {this.props.label} couldn&apos;t render
          </div>
          <p className="mt-1 text-xs text-amber-700/80 dark:text-amber-400/80">
            The rest of the results page is unaffected — you can still
            download the CSV below.
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-amber-500/10 px-2 py-1 text-[10px] text-amber-800 dark:text-amber-300">
            {this.state.error.message}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}
