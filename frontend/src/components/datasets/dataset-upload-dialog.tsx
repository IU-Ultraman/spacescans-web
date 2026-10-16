"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, FileUp, Loader2, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, type CustomBoundary } from "@/lib/api";
import {
  BOUNDARY_LAYERS,
  DATASET_KINDS,
  KIND_INFO,
  MAX_DESCRIPTION,
  MAX_NAME,
  MAX_SHORT_FIELD,
  MAX_VARIABLE_NAME,
  MAX_VARIABLES,
  TEMPORAL_BY_KIND,
  TEMPORAL_LABEL,
  buildDatasetMetadata,
  columnSlug,
  defaultDistanceName,
  guessColumns,
  guessPeriod,
  matchingNote,
  nameProblem,
  parseCsvHead,
  periodProblems,
  profileColumns,
  temporalHint,
  variableNameProblem,
  yearFromFilename,
  type BoundaryLayer,
  type ColumnProfile,
  type CsvHead,
  type DatasetDescription,
  type DatasetKind,
  type DatasetSpec,
  type DatasetTemporal,
  type RegisteredDataset,
} from "@/lib/datasets";
import { cn } from "@/lib/utils";
import { DatasetFormatGuide } from "./dataset-format-guide";
import { ShareToggle } from "./share-toggle";

/** How much of a CSV is read in the browser to offer the column choices. */
const HEAD_BYTES = 256 * 1024;
const RASTER_EXT = /\.tiff?$/i;
const FEATURE_EXT = /\.(gpkg|geojson|json|zip)$/i;

interface RasterRow {
  file: File;
  year: string;
  start: string;
  end: string;
}

interface BandRow {
  name: string;
  band: string;
  unit: string;
  description: string;
  /** False while the first row's name still follows the dataset name. */
  touched: boolean;
}

interface FeatureRow {
  file: File;
  year: string;
}

const FIRST_BAND: BandRow = { name: "", band: "1", unit: "", description: "", touched: false };

/** A first guess at a dataset name: the file's stem without dates, years and
 *  separators. */
function nameFromFile(filename: string): string {
  return filename
    .replace(/\.[A-Za-z0-9]+$/, "")
    .replace(/(?<!\d)(?:\d{4}[-_.]?\d{2}[-_.]?\d{2}|\d{7}|(?:19|20)\d{2})(?!\d)/g, " ")
    .replace(/[-_.]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_NAME);
}

function byName(a: File, b: File): number {
  return a.name.localeCompare(b.name, undefined, { numeric: true });
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} byte${n === 1 ? "" : "s"}`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function ChoiceButton({
  selected, onClick, children, disabled = false,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected}
      className={cn(
        "rounded-md border px-3 py-1.5 text-left text-xs transition-colors disabled:opacity-50",
        selected
          ? "border-primary bg-primary/10 text-foreground"
          : "text-muted-foreground hover:bg-muted/60",
      )}
    >
      {children}
    </button>
  );
}

interface DatasetUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The new dataset, or null when the server's reply did not describe it
   *  (the caller reloads its list either way). */
  onCreated: (dataset: RegisteredDataset | null) => void | Promise<void>;
}

/**
 * Register a dataset: say what it is and how it changes over time, choose the
 * files, say what their parts mean, describe it, choose who can use it.
 *
 * The server validates and prepares the data once (PHASE_D §2.2); tasks reuse
 * the prepared copy. The form asks explicitly for what a guess could get
 * wrong (the area-code column, each file's period), because a wrong guess
 * gives a dataset that links nothing.
 */
export function DatasetUploadDialog({ open, onOpenChange, onCreated }: DatasetUploadDialogProps) {
  const [kind, setKind] = useState<DatasetKind>("polygon_table");
  const [temporal, setTemporal] = useState<DatasetTemporal>("static");

  // --- describe ---
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [source, setSource] = useState("");
  const [version, setVersion] = useState("");
  const [licenseNote, setLicenseNote] = useState("");
  const [shared, setShared] = useState(false);

  // --- area table ---
  // null = not checked (still loading, or the deployment does not say).
  const [boundaries, setBoundaries] = useState<CustomBoundary[] | null>(null);
  const [boundariesChecked, setBoundariesChecked] = useState(false);
  const [geography, setGeography] = useState<BoundaryLayer>("Tract");
  const [tableFile, setTableFile] = useState<File | null>(null);
  const [head, setHead] = useState<CsvHead | null>(null);
  const [profiles, setProfiles] = useState<ColumnProfile[]>([]);
  const [keyColumn, setKeyColumn] = useState("");
  const [timeColumn, setTimeColumn] = useState("");
  const [valueColumns, setValueColumns] = useState<string[]>([]);
  const [colUnits, setColUnits] = useState<Record<string, string>>({});
  const [colDescriptions, setColDescriptions] = useState<Record<string, string>>({});

  // --- raster ---
  const [rasterRows, setRasterRows] = useState<RasterRow[]>([]);
  const [bands, setBands] = useState<BandRow[]>([FIRST_BAND]);

  // --- features ---
  const [featureRows, setFeatureRows] = useState<FeatureRow[]>([]);
  const [featureYearMode, setFeatureYearMode] = useState<"files" | "column">("files");
  const [featureYearColumn, setFeatureYearColumn] = useState("");
  const [featureVar, setFeatureVar] = useState("");
  const [featureVarTouched, setFeatureVarTouched] = useState(false);
  const [featureVarDescription, setFeatureVarDescription] = useState("");

  // --- submit ---
  const [reading, setReading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<{ message: string; issues: string[] } | null>(null);
  // Bumped to remount the file inputs, so a stale selection clears.
  const [inputKey, setInputKey] = useState(0);
  // The dialog scrolls; a refusal from the server must not land out of view.
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) errorRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [error]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setBoundariesChecked(false);
    api
      .listCustomBoundaries()
      .then((res) => {
        if (cancelled) return;
        setBoundaries(res.boundaries);
        const usable = res.boundaries.filter((b) => b.available);
        setGeography((cur) =>
          usable.some((b) => b.boundary === cur) ? cur : (usable[0]?.boundary ?? cur),
        );
      })
      .catch(() => !cancelled && setBoundaries(null))
      .finally(() => !cancelled && setBoundariesChecked(true));
    return () => {
      cancelled = true;
    };
  }, [open]);

  const reset = () => {
    setKind("polygon_table");
    setTemporal("static");
    setName(""); setDescription(""); setSource(""); setVersion(""); setLicenseNote(""); setShared(false);
    setTableFile(null); setHead(null); setProfiles([]); setKeyColumn(""); setTimeColumn("");
    setValueColumns([]); setColUnits({}); setColDescriptions({});
    setRasterRows([]); setBands([FIRST_BAND]);
    setFeatureRows([]); setFeatureYearMode("files"); setFeatureYearColumn("");
    setFeatureVar(""); setFeatureVarTouched(false); setFeatureVarDescription("");
    setReading(false); setUploading(false); setProgress(0); setError(null);
    setInputKey((k) => k + 1);
  };

  const close = (next: boolean) => {
    if (!next && uploading) return; // the upload would carry on unseen
    if (!next) reset();
    onOpenChange(next);
  };

  // Each kind keeps its own files; a new time structure re-reads the periods
  // from the file names and the time column from the table.
  const chooseTemporal = (next: DatasetTemporal) => {
    setTemporal(next);
    setError(null);
    setRasterRows((rows) => rows.map((r) => ({ ...r, ...guessPeriod(r.file.name, next) })));
    setFeatureRows((rows) => rows.map((r) => ({ ...r, year: String(yearFromFilename(r.file.name) ?? "") })));
    const time = next === "static" ? "" : guessColumns(profiles, next).time;
    setTimeColumn(time === keyColumn ? "" : time);
    if (time) setValueColumns((cols) => cols.filter((c) => c !== time));
  };

  const chooseKind = (next: DatasetKind) => {
    setKind(next);
    setError(null);
    if (!TEMPORAL_BY_KIND[next].includes(temporal)) chooseTemporal("static");
  };

  // ------------------------------------------------------------ area table ---

  const pickTable = async (file: File | null) => {
    setTableFile(file);
    setHead(null); setProfiles([]); setKeyColumn(""); setTimeColumn(""); setValueColumns([]);
    setError(null);
    if (!file) return;
    if (!name.trim()) setName(nameFromFile(file.name));
    setReading(true);
    try {
      const text = await file.slice(0, HEAD_BYTES).text();
      const h = parseCsvHead(text, 50, file.size <= HEAD_BYTES);
      if (h.columns.length === 0) {
        setError({ message: "That file has no header row.", issues: [] });
        return;
      }
      const p = profileColumns(h);
      setHead(h);
      setProfiles(p);
      const guess = guessColumns(p, temporal);
      setKeyColumn(guess.key);
      setTimeColumn(guess.time);
    } catch {
      setError({ message: "Could not read that file.", issues: [] });
    } finally {
      setReading(false);
    }
  };

  const chooseKey = (col: string) => {
    setKeyColumn(col);
    setValueColumns((cols) => cols.filter((c) => c !== col));
  };
  const chooseTime = (col: string) => {
    setTimeColumn(col);
    setValueColumns((cols) => cols.filter((c) => c !== col));
  };
  const toggleValue = (col: string, checked: boolean) =>
    setValueColumns((cols) => (checked ? [...cols.filter((c) => c !== col), col] : cols.filter((c) => c !== col)));
  const candidateValues = (head?.columns ?? []).filter(
    (c, i, all) => c && c !== keyColumn && c !== timeColumn && all.indexOf(c) === i,
  );
  const numericShare = (col: string) => profiles.find((p) => p.name === col)?.numericShare ?? 0;
  const selectNumeric = () =>
    setValueColumns(candidateValues.filter((c) => numericShare(c) >= 0.9).slice(0, MAX_VARIABLES));

  const usableBoundaries = boundaries?.filter((b) => b.available) ?? null;
  const geographyChoices: { value: BoundaryLayer; label: string; keyLen: number }[] = usableBoundaries
    ? usableBoundaries.map((b) => ({ value: b.boundary, label: b.label, keyLen: b.key_len }))
    : [...BOUNDARY_LAYERS];
  const keyLen = geographyChoices.find((g) => g.value === geography)?.keyLen ?? null;

  // ---------------------------------------------------------------- raster ---

  const pickRasters = (list: FileList | null) => {
    const files = list ? Array.from(list).sort(byName) : [];
    setError(null);
    setRasterRows(files.map((f) => ({ file: f, ...guessPeriod(f.name, temporal) })));
    if (files.length && !name.trim()) setName(nameFromFile(files[0].name));
  };
  const setRasterRow = (i: number, patch: Partial<RasterRow>) =>
    setRasterRows((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  // The first band's column follows the dataset name until edited, so two
  // rasters do not both arrive as "value".
  const bandNames = bands.map((b, i) => (i === 0 && !b.touched ? columnSlug(name, "value") : b.name));
  const setBand = (i: number, patch: Partial<BandRow>) =>
    setBands((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addBand = () =>
    setBands((rows) => {
      const used = new Set(rows.map((r) => Number(r.band)));
      let n = 1;
      while (used.has(n)) n++;
      return [...rows, { name: `${columnSlug(name, "band")}_b${n}`.slice(0, MAX_VARIABLE_NAME), band: String(n), unit: "", description: "", touched: true }];
    });

  // -------------------------------------------------------------- features ---

  const pickFeatures = (list: FileList | null) => {
    const files = list ? Array.from(list).sort(byName) : [];
    setError(null);
    setFeatureRows(files.map((f) => ({ file: f, year: String(yearFromFilename(f.name) ?? "") })));
    if (files.length && !name.trim()) setName(nameFromFile(files[0].name));
  };
  const featureVarName = featureVarTouched ? featureVar : defaultDistanceName(name);
  const featureMultiple = temporal === "yearly" && featureYearMode === "files";

  // -------------------------------------------------------------- problems ---

  function tableProblems(): string[] {
    if (!tableFile) return ["Choose the CSV file."];
    if (!head) return [reading ? "Reading the file…" : "The file could not be read."];
    const out: string[] = [];
    if (usableBoundaries && usableBoundaries.length === 0) out.push("This deployment has no boundary layers for area tables.");
    const dupes = head.columns.filter((c, i) => head.columns.indexOf(c) !== i);
    if (dupes.length) out.push(`The header repeats ${Array.from(new Set(dupes)).map((d) => `"${d}"`).join(", ")}.`);
    if (!keyColumn) out.push("Choose the column with the area codes.");
    if (temporal !== "static" && !timeColumn) {
      out.push(temporal === "yearly" ? "Choose the year column." : "Choose the date column.");
    }
    if (valueColumns.length === 0) out.push("Select at least one value column.");
    if (valueColumns.length > MAX_VARIABLES) out.push(`Select at most ${MAX_VARIABLES} value columns.`);
    for (const c of valueColumns) {
      const p = variableNameProblem(c, valueColumns.filter((o) => o !== c), false);
      if (p) {
        out.push(`${c}: ${p}`);
        break;
      }
    }
    return out;
  }

  function rasterProblems(): string[] {
    const out: string[] = [];
    const notTiff = rasterRows.find((r) => !RASTER_EXT.test(r.file.name));
    if (notTiff) out.push(`${notTiff.file.name} is not a GeoTIFF (.tif).`);
    out.push(...periodProblems(rasterRows.map((r) => ({ file: r.file.name, year: r.year, start: r.start, end: r.end })), temporal));
    if (bands.length > MAX_VARIABLES) out.push(`List at most ${MAX_VARIABLES} bands.`);
    bands.forEach((b, i) => {
      const p = variableNameProblem(bandNames[i], bandNames.filter((_, j) => j !== i), true);
      if (p) out.push(`Band row ${i + 1}: ${p}`);
      const n = Number(b.band);
      if (!Number.isInteger(n) || n < 1) out.push(`Band row ${i + 1}: the band is a whole number from 1.`);
    });
    if (new Set(bands.map((b) => Number(b.band))).size !== bands.length) out.push("Two rows read the same band.");
    return out;
  }

  function featureProblems(): string[] {
    const out: string[] = [];
    if (featureRows.length === 0) return ["Choose the file" + (featureMultiple ? "s." : ".")];
    const wrong = featureRows.find((r) => !FEATURE_EXT.test(r.file.name));
    if (wrong) out.push(`${wrong.file.name} is not a GeoPackage, GeoJSON or zipped shapefile.`);
    if (!featureMultiple && featureRows.length > 1) out.push("Choose one file.");
    if (featureMultiple) {
      if (!featureRows.every((r) => /^(?:19|20)\d{2}$/.test(r.year.trim()))) out.push("Give every file a four-digit year.");
      else if (new Set(featureRows.map((r) => r.year.trim())).size !== featureRows.length) out.push("Two files have the same year.");
    }
    if (temporal === "yearly" && featureYearMode === "column" && !featureYearColumn.trim()) {
      out.push("Name the attribute that holds the year.");
    }
    const p = variableNameProblem(featureVarName, [], true);
    if (p) out.push(`Result column: ${p}`);
    return out;
  }

  const kindProblems =
    kind === "polygon_table" ? tableProblems() : kind === "raster" ? rasterProblems() : featureProblems();
  const problems = [...kindProblems, ...[nameProblem(name)].filter((p): p is string => !!p)];
  const canSave = problems.length === 0 && !reading && !uploading;

  // ------------------------------------------------------------------ save ---

  const save = async () => {
    const desc: DatasetDescription = {
      name,
      temporal,
      source,
      version,
      description,
      license_note: licenseNote,
      visibility: shared ? "deployment" : "private",
    };
    let spec: DatasetSpec;
    let files: File[];
    if (kind === "polygon_table") {
      if (!tableFile) return;
      spec = {
        kind,
        geography,
        keyColumn,
        timeColumn: temporal === "static" ? null : timeColumn,
        variables: valueColumns.map((c) => ({ name: c, unit: colUnits[c], description: colDescriptions[c] })),
      };
      files = [tableFile];
    } else if (kind === "raster") {
      spec = {
        kind,
        files: rasterRows.map((r) => ({ file: r.file.name, year: r.year, start: r.start, end: r.end })),
        variables: bands.map((b, i) => ({
          name: bandNames[i], band: Number(b.band), unit: b.unit, description: b.description,
        })),
      };
      files = rasterRows.map((r) => r.file);
    } else {
      spec = {
        kind,
        variable: { name: featureVarName, description: featureVarDescription },
        yearly:
          temporal !== "yearly"
            ? undefined
            : featureYearMode === "files"
              ? { mode: "files", files: featureRows.map((r) => ({ file: r.file.name, year: r.year })) }
              : { mode: "column", column: featureYearColumn },
      };
      files = featureRows.map((r) => r.file);
    }

    setUploading(true);
    setProgress(0);
    setError(null);
    try {
      const created = await api.createDataset(
        { files, metadata: buildDatasetMetadata(desc, spec) },
        setProgress,
      );
      await onCreated(created);
      reset();
      onOpenChange(false);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? { message: e.message, issues: e.issues }
          : { message: "Could not add the dataset.", issues: [] },
      );
    } finally {
      setUploading(false);
    }
  };

  const fileCount = kind === "polygon_table" ? (tableFile ? 1 : 0) : kind === "raster" ? rasterRows.length : featureRows.length;
  const totalBytes =
    kind === "polygon_table"
      ? tableFile?.size ?? 0
      : (kind === "raster" ? rasterRows : featureRows).reduce((n, r) => n + r.file.size, 0);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Add a dataset</DialogTitle>
          <DialogDescription>
            Register your own exposure data once and select it in any of your
            tasks. It is checked and prepared on the server when you add it;
            tasks reuse the prepared copy.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {/* 1. kind */}
          <section className="space-y-2">
            <Label>1. What are you adding?</Label>
            <div className="grid gap-2 sm:grid-cols-3">
              {DATASET_KINDS.map((k) => (
                <ChoiceButton key={k} selected={kind === k} onClick={() => chooseKind(k)} disabled={uploading}>
                  <span className="block font-medium">{KIND_INFO[k].label}</span>
                  <span className="mt-0.5 block opacity-80">{KIND_INFO[k].blurb}</span>
                </ChoiceButton>
              ))}
            </div>
          </section>

          {/* 2. time structure */}
          <section className="space-y-2">
            <Label>2. Do the values change over time?</Label>
            <div className="flex flex-wrap gap-2">
              {TEMPORAL_BY_KIND[kind].map((t) => (
                <ChoiceButton key={t} selected={temporal === t} onClick={() => chooseTemporal(t)} disabled={uploading}>
                  <span className="font-medium">{TEMPORAL_LABEL[t]}</span>
                  <span className="ml-1.5 opacity-70">— {temporalHint(kind, t)}</span>
                </ChoiceButton>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">{matchingNote(temporal)}</p>
          </section>

          {kind === "polygon_table" && (
            <section className="space-y-2">
              <span className="text-xs text-muted-foreground">Which areas do the rows describe?</span>
              {!boundariesChecked ? (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" /> Checking what this deployment provides…
                </div>
              ) : usableBoundaries && usableBoundaries.length === 0 ? (
                <p className="text-xs text-destructive">
                  This deployment has no boundary layers provisioned, so area values could
                  not be linked. Add one on the Data Setup page first, or add a raster or
                  features instead.
                </p>
              ) : (
                <>
                  <div className="flex flex-wrap gap-2">
                    {geographyChoices.map((g) => (
                      <ChoiceButton key={g.value} selected={geography === g.value} onClick={() => setGeography(g.value)} disabled={uploading}>
                        {g.label}
                      </ChoiceButton>
                    ))}
                  </div>
                  {!usableBoundaries && (
                    <p className="text-xs text-muted-foreground">
                      Could not check which boundary layers this deployment provides; the
                      server checks when you add the dataset.
                    </p>
                  )}
                </>
              )}
            </section>
          )}

          <DatasetFormatGuide kind={kind} temporal={temporal} geography={geography} keyLen={keyLen} />

          {/* 3. files */}
          {kind === "polygon_table" && (
            <section className="space-y-2">
              <Label htmlFor="dataset-csv">3. Your CSV</Label>
              <div className="flex items-center gap-3">
                <Input
                  id="dataset-csv"
                  key={`csv-${inputKey}`}
                  type="file"
                  accept={KIND_INFO.polygon_table.accept}
                  onChange={(e) => void pickTable(e.target.files?.[0] ?? null)}
                  disabled={uploading}
                  className="cursor-pointer"
                />
                {reading && <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />}
              </div>
              {tableFile && head && (
                <p className="text-xs text-muted-foreground">
                  <FileUp className="mr-1 inline size-3" />
                  {head.columns.length} columns · {formatBytes(tableFile.size)}. Only the first
                  rows are read here, to offer the columns; the whole file is checked on the server.
                </p>
              )}
            </section>
          )}

          {kind === "polygon_table" && head && (
            <section className="space-y-3">
              <Label>4. Which column is which?</Label>
              <div className={cn("grid gap-3", temporal !== "static" && "sm:grid-cols-2")}>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Area code</span>
                  <select
                    value={keyColumn}
                    onChange={(e) => chooseKey(e.target.value)}
                    disabled={uploading}
                    className={cn("w-full rounded-md border bg-background px-2 py-1.5 text-sm", !keyColumn && "border-destructive/60")}
                  >
                    <option value="">Select a column…</option>
                    {head.columns.filter((c) => c && c !== timeColumn).map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
                {temporal !== "static" && (
                  <div className="space-y-1">
                    <span className="text-xs text-muted-foreground">
                      {temporal === "yearly" ? "Year" : "Date (YYYY-MM-DD)"}
                    </span>
                    <select
                      value={timeColumn}
                      onChange={(e) => chooseTime(e.target.value)}
                      disabled={uploading}
                      className={cn("w-full rounded-md border bg-background px-2 py-1.5 text-sm", !timeColumn && "border-destructive/60")}
                    >
                      <option value="">Select the {temporal === "yearly" ? "year" : "date"} column…</option>
                      {head.columns.filter((c) => c && c !== keyColumn).map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              <div className="space-y-1">
                <div className="flex items-baseline gap-3">
                  <span className="text-xs text-muted-foreground">
                    Value columns ({valueColumns.length} selected; each becomes a result column)
                  </span>
                  <button type="button" className="ml-auto text-xs text-primary hover:underline" onClick={selectNumeric}>
                    Select numeric
                  </button>
                  <button type="button" className="text-xs text-primary hover:underline" onClick={() => setValueColumns([])}>
                    Clear
                  </button>
                </div>
                <div className="max-h-64 overflow-y-auto rounded-md border p-1">
                  {candidateValues.map((c) => {
                    const checked = valueColumns.includes(c);
                    return (
                      <div key={c} className="rounded hover:bg-muted/60">
                        <label className="flex cursor-pointer items-center gap-2 px-2 py-1">
                          <Checkbox checked={checked} onCheckedChange={(next) => toggleValue(c, next === true)} />
                          <span className="min-w-0 flex-1 truncate text-sm">{c}</span>
                          {numericShare(c) < 0.5 && (
                            <span className="shrink-0 text-xs text-muted-foreground">mostly not numeric</span>
                          )}
                        </label>
                        {checked && (
                          <div className="grid gap-2 px-2 pb-2 pl-8 sm:grid-cols-2">
                            <Input
                              value={colUnits[c] ?? ""}
                              onChange={(e) => setColUnits((m) => ({ ...m, [c]: e.target.value }))}
                              maxLength={50}
                              placeholder="Unit (optional), e.g. index, ug/m3"
                              aria-label={`Unit of ${c}`}
                              className="h-8 text-xs"
                            />
                            <Input
                              value={colDescriptions[c] ?? ""}
                              onChange={(e) => setColDescriptions((m) => ({ ...m, [c]: e.target.value }))}
                              maxLength={MAX_SHORT_FIELD}
                              placeholder="What it measures (optional)"
                              aria-label={`Description of ${c}`}
                              className="h-8 text-xs"
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {candidateValues.length === 0 && (
                    <p className="px-2 py-1 text-xs text-muted-foreground">No other columns in this file.</p>
                  )}
                </div>
              </div>
            </section>
          )}

          {kind === "raster" && (
            <section className="space-y-2">
              <Label htmlFor="dataset-rasters">
                3. {temporal === "static" ? "Your GeoTIFF" : `Your GeoTIFFs, one per ${temporal === "yearly" ? "year" : temporal === "daily" ? "day" : "two-week period"}`}
              </Label>
              <Input
                id="dataset-rasters"
                key={`raster-${inputKey}-${temporal}`}
                type="file"
                accept={KIND_INFO.raster.accept}
                multiple={temporal !== "static"}
                onChange={(e) => pickRasters(e.target.files)}
                disabled={uploading}
                className="cursor-pointer"
              />
              {rasterRows.length > 0 && temporal !== "static" && (
                <div className="max-h-64 overflow-auto rounded-md border">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-muted/60 text-muted-foreground">
                      <tr>
                        <th className="px-2 py-1.5 text-left font-medium">File</th>
                        {temporal === "yearly" && <th className="px-2 py-1.5 text-left font-medium">Year</th>}
                        {temporal !== "yearly" && <th className="px-2 py-1.5 text-left font-medium">{temporal === "daily" ? "Day" : "Start"}</th>}
                        {temporal === "biweekly" && <th className="px-2 py-1.5 text-left font-medium">End</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {rasterRows.map((r, i) => (
                        <tr key={r.file.name + i} className="border-t">
                          <td className="max-w-[16rem] truncate px-2 py-1" title={r.file.name}>{r.file.name}</td>
                          {temporal === "yearly" ? (
                            <td className="px-2 py-1">
                              <Input value={r.year} onChange={(e) => setRasterRow(i, { year: e.target.value })} inputMode="numeric" maxLength={4} placeholder="YYYY" aria-label={`Year of ${r.file.name}`} className="h-7 w-20 text-xs" />
                            </td>
                          ) : (
                            <td className="px-2 py-1">
                              <Input value={r.start} onChange={(e) => setRasterRow(i, temporal === "daily" ? { start: e.target.value, end: e.target.value } : { start: e.target.value })} maxLength={10} placeholder="YYYY-MM-DD" aria-label={`Start of ${r.file.name}`} className="h-7 w-28 text-xs" />
                            </td>
                          )}
                          {temporal === "biweekly" && (
                            <td className="px-2 py-1">
                              <Input value={r.end} onChange={(e) => setRasterRow(i, { end: e.target.value })} maxLength={10} placeholder="YYYY-MM-DD" aria-label={`End of ${r.file.name}`} className="h-7 w-28 text-xs" />
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {rasterRows.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {rasterRows.length} file{rasterRows.length === 1 ? "" : "s"} · {formatBytes(totalBytes)}
                </p>
              )}
            </section>
          )}

          {kind === "raster" && (
            <section className="space-y-2">
              <Label>4. What do the pixels hold?</Label>
              <p className="text-xs text-muted-foreground">
                One row per band to link; each becomes a result column. Most files have one band.
              </p>
              <div className="space-y-2">
                {bands.map((b, i) => {
                  const problem = variableNameProblem(bandNames[i], bandNames.filter((_, j) => j !== i), true);
                  return (
                    <div key={i} className="rounded-md border p-2">
                      <div className="grid gap-2 sm:grid-cols-[1fr_5rem_1fr_auto]">
                        <Input
                          value={bandNames[i]}
                          onChange={(e) => setBand(i, { name: e.target.value, touched: true })}
                          maxLength={MAX_VARIABLE_NAME}
                          placeholder="Result column, e.g. pm25"
                          aria-label={`Result column of band row ${i + 1}`}
                          className={cn("h-8 text-xs", problem && "border-destructive/60")}
                        />
                        <Input
                          value={b.band}
                          onChange={(e) => setBand(i, { band: e.target.value })}
                          inputMode="numeric"
                          maxLength={3}
                          placeholder="Band"
                          aria-label={`Band number of row ${i + 1}`}
                          className="h-8 text-xs"
                        />
                        <Input
                          value={b.unit}
                          onChange={(e) => setBand(i, { unit: e.target.value })}
                          maxLength={50}
                          placeholder="Unit (optional)"
                          aria-label={`Unit of band row ${i + 1}`}
                          className="h-8 text-xs"
                        />
                        <button
                          type="button"
                          onClick={() => setBands((rows) => rows.filter((_, j) => j !== i))}
                          disabled={bands.length === 1}
                          aria-label={`Remove band row ${i + 1}`}
                          className="rounded p-1 text-muted-foreground hover:text-destructive disabled:opacity-30"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </div>
                      <Input
                        value={b.description}
                        onChange={(e) => setBand(i, { description: e.target.value })}
                        maxLength={MAX_SHORT_FIELD}
                        placeholder="What it measures (optional)"
                        aria-label={`Description of band row ${i + 1}`}
                        className="mt-2 h-8 text-xs"
                      />
                      {problem && <p className="mt-1 text-xs text-destructive">{problem}</p>}
                    </div>
                  );
                })}
              </div>
              <Button type="button" variant="outline" size="sm" onClick={addBand} disabled={bands.length >= MAX_VARIABLES}>
                <Plus className="size-4" /> Add another band
              </Button>
            </section>
          )}

          {kind === "features" && (
            <section className="space-y-2">
              <Label htmlFor="dataset-features">3. Your features</Label>
              {temporal === "yearly" && (
                <div className="flex flex-wrap gap-2">
                  <ChoiceButton selected={featureYearMode === "files"} onClick={() => { setFeatureYearMode("files"); setFeatureRows([]); setInputKey((k) => k + 1); }} disabled={uploading}>
                    One file per year
                  </ChoiceButton>
                  <ChoiceButton selected={featureYearMode === "column"} onClick={() => { setFeatureYearMode("column"); setFeatureRows([]); setInputKey((k) => k + 1); }} disabled={uploading}>
                    One file with a year attribute
                  </ChoiceButton>
                </div>
              )}
              <Input
                id="dataset-features"
                key={`features-${inputKey}-${temporal}-${featureYearMode}`}
                type="file"
                accept={KIND_INFO.features.accept}
                multiple={featureMultiple}
                onChange={(e) => pickFeatures(e.target.files)}
                disabled={uploading}
                className="cursor-pointer"
              />
              {featureMultiple && featureRows.length > 0 && (
                <div className="max-h-56 overflow-auto rounded-md border">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-muted/60 text-muted-foreground">
                      <tr>
                        <th className="px-2 py-1.5 text-left font-medium">File</th>
                        <th className="px-2 py-1.5 text-left font-medium">Year</th>
                      </tr>
                    </thead>
                    <tbody>
                      {featureRows.map((r, i) => (
                        <tr key={r.file.name + i} className="border-t">
                          <td className="max-w-[16rem] truncate px-2 py-1" title={r.file.name}>{r.file.name}</td>
                          <td className="px-2 py-1">
                            <Input
                              value={r.year}
                              onChange={(e) => setFeatureRows((rows) => rows.map((x, j) => (j === i ? { ...x, year: e.target.value } : x)))}
                              inputMode="numeric"
                              maxLength={4}
                              placeholder="YYYY"
                              aria-label={`Year of ${r.file.name}`}
                              className="h-7 w-20 text-xs"
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {temporal === "yearly" && featureYearMode === "column" && (
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Attribute holding the year</span>
                  <Input
                    value={featureYearColumn}
                    onChange={(e) => setFeatureYearColumn(e.target.value)}
                    maxLength={MAX_VARIABLE_NAME}
                    placeholder="e.g. year"
                    className="h-8 max-w-xs text-xs"
                  />
                </div>
              )}
              {featureRows.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {featureRows.length} file{featureRows.length === 1 ? "" : "s"} · {formatBytes(totalBytes)}
                </p>
              )}

              <div className="grid gap-2 pt-2 sm:grid-cols-2">
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">Result column (distance in metres)</span>
                  <Input
                    value={featureVarName}
                    onChange={(e) => {
                      setFeatureVar(e.target.value);
                      setFeatureVarTouched(true);
                    }}
                    maxLength={MAX_VARIABLE_NAME}
                    placeholder="e.g. parks_dist_m"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">What it measures (optional)</span>
                  <Input
                    value={featureVarDescription}
                    onChange={(e) => setFeatureVarDescription(e.target.value)}
                    maxLength={MAX_SHORT_FIELD}
                    placeholder="e.g. Distance to the nearest park"
                    className="h-8 text-xs"
                  />
                </div>
              </div>
            </section>
          )}

          {/* describe */}
          <section className="space-y-3">
            <Label>{kind === "features" ? "4" : "5"}. Describe it</Label>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1 sm:col-span-2">
                <span className="text-xs text-muted-foreground">Name</span>
                <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={MAX_NAME} placeholder="e.g. Neighborhood greenness" />
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">Source (optional)</span>
                <Input value={source} onChange={(e) => setSource(e.target.value)} maxLength={MAX_SHORT_FIELD} placeholder="Who produced the data" />
              </div>
              <div className="space-y-1">
                <span className="text-xs text-muted-foreground">Version (optional)</span>
                <Input value={version} onChange={(e) => setVersion(e.target.value)} maxLength={MAX_SHORT_FIELD} placeholder="e.g. v2.1, 2024 release" />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <span className="text-xs text-muted-foreground">Description (optional)</span>
                <Textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={MAX_DESCRIPTION} rows={2} placeholder="What the values mean and how they were made." />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <span className="text-xs text-muted-foreground">Terms of use (optional)</span>
                <Input value={licenseNote} onChange={(e) => setLicenseNote(e.target.value)} maxLength={MAX_SHORT_FIELD} placeholder="e.g. Restricted to the study team; no redistribution" />
              </div>
            </div>
          </section>

          <section className="space-y-2">
            <Label>{kind === "features" ? "5" : "6"}. Who can use it?</Label>
            <ShareToggle checked={shared} onChange={setShared} disabled={uploading} />
            {!shared && <p className="text-xs text-muted-foreground">Private: only you can see and select it. You can share it later.</p>}
          </section>

          {error && (
            <div
              ref={errorRef}
              role="alert"
              className="flex gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div className="min-w-0 space-y-1">
                <p>{error.message}</p>
                {error.issues.length > 0 && (
                  <ul className="list-disc space-y-0.5 pl-4">
                    {error.issues.map((issue, i) => (
                      <li key={i} className="break-words">{issue}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}

          {uploading && (
            <div className="space-y-1">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
              </div>
              <p className="text-xs text-muted-foreground">
                {progress < 100
                  ? `Uploading ${fileCount} file${fileCount === 1 ? "" : "s"}… ${progress}%`
                  : "Uploaded. Checking and preparing the data on the server…"}
              </p>
            </div>
          )}
        </div>

        <DialogFooter className="items-center gap-2 sm:justify-between">
          <p className="text-xs text-muted-foreground">
            {!uploading && problems.length > 0 ? problems[0] : ""}
          </p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => close(false)} disabled={uploading}>
              Cancel
            </Button>
            <Button onClick={() => void save()} disabled={!canSave}>
              {uploading && <Loader2 className="size-4 animate-spin" />}
              Add dataset
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
