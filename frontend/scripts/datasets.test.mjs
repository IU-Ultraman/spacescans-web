// Pure logic of registered datasets (src/lib/datasets.ts), via the tsc-emitted
// JS in .next-check (npm run check:lib). Synthetic values only.
import test from "node:test";
import assert from "node:assert/strict";
import {
  TEMPORAL_BY_KIND,
  temporalHint,
  matchingNote,
  yearFromFilename,
  datesFromFilename,
  guessPeriod,
  addDays,
  isIsoDate,
  periodProblems,
  parseCsvHead,
  profileColumns,
  guessColumns,
  buildDatasetMetadata,
  nameProblem,
  variableNameProblem,
  defaultDistanceName,
  columnSlug,
  normalizeDatasetList,
  unwrapDataset,
  isSelectable,
  isPending,
  isFailed,
  sortDatasets,
  metadataPatch,
  MAX_VARIABLE_NAME,
} from "../.next-check/lib/datasets.js";

test("each kind offers the time structures the contract allows", () => {
  assert.deepEqual([...TEMPORAL_BY_KIND.polygon_table], ["static", "yearly", "daily"]);
  assert.deepEqual([...TEMPORAL_BY_KIND.raster], ["static", "yearly", "biweekly", "daily"]);
  assert.deepEqual([...TEMPORAL_BY_KIND.features], ["static", "yearly"]);
  assert.match(temporalHint("polygon_table", "daily"), /date column/);
  assert.match(temporalHint("raster", "biweekly"), /two-week/);
  assert.match(matchingNote("daily"), /days it overlaps/);
  assert.match(matchingNote("static"), /whatever its dates/);
});

test("years in file names", () => {
  assert.equal(yearFromFilename("ndvi_2014.tif"), 2014);
  assert.equal(yearFromFilename("dir/sub/ndvi1999.tif"), 1999);
  assert.equal(yearFromFilename("pm25_20140131.tif"), 2014);
  assert.equal(yearFromFilename("layer_v3.tif"), null);
});

test("dates in file names", () => {
  assert.deepEqual(datesFromFilename("pm25_2014-01-31.tif"), ["2014-01-31"]);
  assert.deepEqual(datesFromFilename("pm25_2014_01_31.tif"), ["2014-01-31"]);
  assert.deepEqual(datesFromFilename("pm25_20140131.tif"), ["2014-01-31"]);
  // ACAG style: year + day of year, start-end.
  assert.deepEqual(datesFromFilename("no2_2014001-2014014.tif"), ["2014-01-01", "2014-01-14"]);
  assert.deepEqual(datesFromFilename("x_2016060.tif"), ["2016-02-29"]);
  assert.deepEqual(datesFromFilename("x_2015366.tif"), []); // not a leap year
  assert.deepEqual(datesFromFilename("x_20141301.tif"), []); // month 13
  assert.deepEqual(datesFromFilename("tile_1234567.tif"), []); // year out of range
  assert.deepEqual(datesFromFilename("a_20140101_20140114.tif"), ["2014-01-01", "2014-01-14"]);
  // Mixed separators are not a date.
  assert.deepEqual(datesFromFilename("x_2014-01_31.tif"), []);
});

test("period guesses", () => {
  assert.deepEqual(guessPeriod("ndvi_2015.tif", "yearly"), { year: "2015", start: "", end: "" });
  assert.deepEqual(guessPeriod("t_20150301.tif", "daily"), { year: "", start: "2015-03-01", end: "2015-03-01" });
  assert.deepEqual(guessPeriod("no2_2014001-2014014.tif", "biweekly"), {
    year: "", start: "2014-01-01", end: "2014-01-14",
  });
  assert.deepEqual(guessPeriod("no2_20141225.tif", "biweekly"), {
    year: "", start: "2014-12-25", end: "2015-01-07",
  });
  assert.deepEqual(guessPeriod("nodate.tif", "biweekly"), { year: "", start: "", end: "" });
  assert.equal(addDays("2016-02-28", 1), "2016-02-29");
  assert.ok(isIsoDate("2016-02-29"));
  assert.ok(!isIsoDate("2015-02-29"));
  assert.ok(!isIsoDate("2015-2-1"));
});

test("period problems", () => {
  assert.deepEqual(periodProblems([], "static"), ["Choose at least one file."]);
  assert.deepEqual(periodProblems([{ file: "a.tif" }], "static"), []);
  assert.equal(periodProblems([{ file: "a.tif" }, { file: "b.tif" }], "static").length, 1);
  assert.deepEqual(periodProblems([{ file: "a", year: "2014" }, { file: "b", year: "2015" }], "yearly"), []);
  assert.match(periodProblems([{ file: "a", year: "2014" }, { file: "b", year: "2014" }], "yearly")[0], /same year/);
  assert.match(periodProblems([{ file: "a", year: "14" }], "yearly")[0], /four-digit/);
  assert.deepEqual(periodProblems([{ file: "a", start: "2014-01-01" }, { file: "b", start: "2014-01-02" }], "daily"), []);
  assert.match(periodProblems([{ file: "a", start: "2014-01-01" }, { file: "b", start: "2014-01-01" }], "daily")[0], /same start/);
  assert.match(periodProblems([{ file: "a", start: "" }], "daily")[0], /start date/);
  const ok = [
    { file: "a", start: "2014-01-01", end: "2014-01-14" },
    { file: "b", start: "2014-01-15", end: "2014-01-28" },
  ];
  assert.deepEqual(periodProblems(ok, "biweekly"), []);
  assert.match(periodProblems([{ file: "a", start: "2014-01-01", end: "" }], "biweekly")[0], /end date/);
  assert.match(periodProblems([{ file: "a", start: "2014-01-10", end: "2014-01-01" }], "biweekly")[0], /before its start/);
  const overlap = [
    { file: "b", start: "2014-01-10", end: "2014-01-23" },
    { file: "a", start: "2014-01-01", end: "2014-01-14" },
  ];
  assert.match(periodProblems(overlap, "biweekly")[0], /overlap/);
});

test("CSV header reader", () => {
  const text = '﻿geoid,"name, long",value\r\n12073000200,"say ""hi""",0.5\r\n\r\n12073000301,x,\r\n';
  const head = parseCsvHead(text);
  assert.deepEqual(head.columns, ["geoid", "name, long", "value"]);
  assert.deepEqual(head.rows, [["12073000200", 'say "hi"', "0.5"], ["12073000301", "x", ""]]);

  // A cut-off last record is dropped unless the text is the whole file.
  const partial = "a,b\n1,2\n3,";
  assert.deepEqual(parseCsvHead(partial, 50, false).rows, [["1", "2"]]);
  assert.deepEqual(parseCsvHead(partial, 50, true).rows, [["1", "2"], ["3", ""]]);

  // maxRows caps the data rows; short rows are padded.
  const many = "k,v\n" + Array.from({ length: 10 }, (_, i) => `${i}`).join("\n") + "\n";
  const capped = parseCsvHead(many, 3);
  assert.equal(capped.rows.length, 3);
  assert.deepEqual(capped.rows[0], ["0", ""]);
  assert.deepEqual(parseCsvHead("").columns, []);
});

test("column profiles and first guesses", () => {
  const head = parseCsvHead(
    "tract_id,year,day,ndvi,label\n" +
      "12073000200,2014,2014-01-01,0.3,a\n" +
      "12073000301,2015,2014-01-02,NA,b\n",
  );
  const profiles = profileColumns(head);
  const byName = Object.fromEntries(profiles.map((p) => [p.name, p]));
  assert.equal(byName.ndvi.numericShare, 1); // NA is blank, not text
  assert.equal(byName.label.numericShare, 0);
  assert.ok(byName.year.allYears);
  assert.ok(byName.day.allDates);
  assert.deepEqual(guessColumns(profiles, "static"), { key: "tract_id", time: "" });
  assert.deepEqual(guessColumns(profiles, "yearly"), { key: "tract_id", time: "year" });
  assert.deepEqual(guessColumns(profiles, "daily"), { key: "tract_id", time: "day" });
  const unnamed = profileColumns(parseCsvHead("code,y,v\n12073,2014,1\n"));
  assert.deepEqual(guessColumns(unnamed, "yearly"), { key: "", time: "y" });
});

const desc = (temporal, extra = {}) => ({
  name: "  Greenness ",
  temporal,
  source: " Study X ",
  version: "",
  description: "NDVI per tract",
  license_note: "   ",
  visibility: "private",
  ...extra,
});

test("metadata: area tables", () => {
  const vars = [{ name: "ndvi", unit: " index ", description: "" }, { name: "lst" }];
  const stat = buildDatasetMetadata(desc("static"), {
    kind: "polygon_table", geography: "Tract", keyColumn: "geoid", timeColumn: "year", variables: vars,
  });
  assert.deepEqual(stat, {
    name: "Greenness",
    kind: "polygon_table",
    temporal: "static",
    key: { geography: "Tract", column: "geoid" },
    variables: [{ name: "ndvi", unit: "index" }, { name: "lst" }],
    visibility: "private",
    source: "Study X",
    description: "NDVI per tract",
  });
  const daily = buildDatasetMetadata(desc("daily", { visibility: "deployment" }), {
    kind: "polygon_table", geography: "ZCTA5", keyColumn: "zcta", timeColumn: " date ", variables: vars,
  });
  assert.deepEqual(daily.key, { geography: "ZCTA5", column: "zcta", time_column: "date" });
  assert.equal(daily.visibility, "deployment");
  assert.equal("periods" in daily, false);
});

test("metadata: rasters", () => {
  const variables = [{ name: "pm25", band: 1, unit: "ug/m3" }, { name: "no2", band: 3 }];
  const yearly = buildDatasetMetadata(desc("yearly"), {
    kind: "raster",
    files: [{ file: "a_2014.tif", year: "2014" }, { file: "a_2015.tif", year: " 2015" }],
    variables,
  });
  assert.deepEqual(yearly.periods, [{ file: "a_2014.tif", year: 2014 }, { file: "a_2015.tif", year: 2015 }]);
  assert.deepEqual(yearly.variables, [{ name: "pm25", unit: "ug/m3", band: 1 }, { name: "no2", band: 3 }]);
  assert.equal("key" in yearly, false);

  const biweekly = buildDatasetMetadata(desc("biweekly"), {
    kind: "raster",
    files: [{ file: "b.tif", start: "2014-01-01", end: "2014-01-14" }],
    variables,
  });
  assert.deepEqual(biweekly.periods, [{ file: "b.tif", start: "2014-01-01", end: "2014-01-14" }]);

  const daily = buildDatasetMetadata(desc("daily"), {
    kind: "raster",
    files: [{ file: "d.tif", start: "2014-01-01", end: "2099-01-01" }],
    variables,
  });
  assert.deepEqual(daily.periods, [{ file: "d.tif", start: "2014-01-01", end: "2014-01-01" }]);

  const stat = buildDatasetMetadata(desc("static"), { kind: "raster", files: [{ file: "s.tif" }], variables });
  assert.equal("periods" in stat, false);
});

test("metadata: features", () => {
  const variable = { name: "parks_dist_m", description: "Nearest park" };
  const stat = buildDatasetMetadata(desc("static"), { kind: "features", variable });
  assert.deepEqual(stat.variables, [{ name: "parks_dist_m", unit: "m", description: "Nearest park" }]);
  assert.equal("key" in stat || "periods" in stat, false);

  const files = buildDatasetMetadata(desc("yearly"), {
    kind: "features",
    variable,
    yearly: { mode: "files", files: [{ file: "p2014.gpkg", year: "2014" }, { file: "p2015.gpkg", year: "2015" }] },
  });
  assert.deepEqual(files.periods, [{ file: "p2014.gpkg", year: 2014 }, { file: "p2015.gpkg", year: 2015 }]);

  const column = buildDatasetMetadata(desc("yearly"), {
    kind: "features", variable, yearly: { mode: "column", column: " yr " },
  });
  assert.deepEqual(column.key, { time_column: "yr" });
  assert.equal("periods" in column, false);
});

test("names", () => {
  assert.equal(nameProblem("  "), "Give the dataset a name.");
  assert.match(nameProblem("x".repeat(81)), /80/);
  assert.equal(nameProblem("Greenness"), null);

  assert.equal(variableNameProblem("PM2.5 mean", [], false), null); // CSV headers kept as they are
  assert.match(variableNameProblem("PM2.5", [], true), /letters, digits/);
  assert.match(variableNameProblem("pid", [], false), /already a column/);
  assert.match(variableNameProblem("StartDate", [], true), /already a column/);
  assert.match(variableNameProblem("ndvi", ["NDVI"], true), /ignoring case/);
  assert.match(variableNameProblem("a".repeat(41), [], true), /40/);

  assert.equal(columnSlug("Tree canopy (%)", "value"), "tree_canopy");
  assert.equal(columnSlug("2019 NDVI", "value"), "f_2019_ndvi");
  assert.equal(columnSlug("!!", "value"), "value");
  assert.equal(columnSlug("abc_def_ghi", "x", 4), "abc");
  assert.equal(defaultDistanceName("City parks"), "city_parks_dist_m");
  assert.equal(defaultDistanceName("123 sites!"), "f_123_sites_dist_m");
  assert.equal(defaultDistanceName("   "), "feature_dist_m");
  assert.equal(defaultDistanceName("公园"), "feature_dist_m");
  const long = defaultDistanceName("A very long name for a features dataset of many parts");
  assert.ok(long.length <= MAX_VARIABLE_NAME, long);
  assert.ok(long.endsWith("_dist_m") && !long.includes("__"), long);
});

const row = (over = {}) => ({
  id: "a1",
  name: "Mine",
  kind: "raster",
  temporal: "yearly",
  variables: [{ name: "v", unit: "u" }],
  visibility: "private",
  owned_by_me: true,
  owner_display: "me",
  created_at: "2026-10-01T00:00:00Z",
  status: "ready",
  ...over,
});

test("reading list and dataset replies", () => {
  assert.equal(normalizeDatasetList([row()]).length, 1);
  assert.equal(normalizeDatasetList({ datasets: [row(), { name: "no id" }] }).length, 1);
  assert.throws(() => normalizeDatasetList({ items: [] }));

  const d = unwrapDataset({ dataset: row({ visibility: "public", owned_by_me: "yes", variables: ["a", { name: "b" }, 3] }) });
  assert.equal(d.visibility, "private"); // anything but "deployment" reads as private
  assert.equal(d.owned_by_me, false); // only a real true
  assert.deepEqual(d.variables, [{ name: "a" }, { name: "b" }]);
  const legacy = unwrapDataset({ id: "b2", created_utc: "2026-01-01T00:00:00Z" });
  assert.equal(legacy.name, "b2");
  assert.equal(legacy.created_at, "2026-01-01T00:00:00Z");
  assert.deepEqual(legacy.variables, []);
  assert.throws(() => unwrapDataset({ status: "ok" }));
});

test("status", () => {
  assert.ok(isSelectable(row({ status: undefined })));
  assert.ok(isSelectable(row({ status: "ready" })));
  assert.ok(isPending(row({ status: "Preparing" })) && !isSelectable(row({ status: "preparing" })));
  assert.ok(isFailed(row({ status: "failed" })) && !isSelectable(row({ status: "error" })));
});

test("sorting: own first, newest first, then by name", () => {
  const sorted = sortDatasets([
    row({ id: "s", name: "Shared", owned_by_me: false, created_at: "2026-10-09" }),
    row({ id: "o1", name: "B", created_at: "2026-10-01" }),
    row({ id: "o2", name: "A", created_at: "2026-10-01" }),
    row({ id: "o3", name: "C", created_at: "2026-10-05" }),
  ]);
  assert.deepEqual(sorted.map((d) => d.id), ["o3", "o2", "o1", "s"]);
});

test("edit patch carries only what changed", () => {
  const before = unwrapDataset(row({ description: "old", source: null, version: "1" }));
  const same = {
    name: "Mine", description: "old", source: "", version: "1", license_note: "",
    variables: [{ name: "v", unit: "u", description: "" }],
  };
  assert.deepEqual(metadataPatch(before, same), {});
  const changed = metadataPatch(before, {
    ...same, name: " Mine 2 ", source: "Lab", variables: [{ name: "v", unit: "ug/m3", description: "PM" }],
  });
  assert.deepEqual(changed, {
    name: "Mine 2",
    source: "Lab",
    variables: [{ name: "v", unit: "ug/m3", description: "PM" }],
  });
});
