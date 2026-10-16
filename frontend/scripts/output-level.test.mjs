// Output-level helpers (src/lib/output-level.ts), via the tsc-emitted JS.
import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_OUTPUT_LEVEL,
  OUTPUT_LEVEL_INFO,
  isOutputLevel,
  resultLevel,
  unitNoun,
  countLabel,
  hasStateColumn,
  linkageRate,
} from "../.next-check/lib/output-level.js";

test("participant is the default", () => {
  assert.equal(DEFAULT_OUTPUT_LEVEL, "participant");
  assert.ok(isOutputLevel("episode") && isOutputLevel("participant"));
  assert.ok(!isOutputLevel("patient") && !isOutputLevel(undefined));
  assert.match(OUTPUT_LEVEL_INFO.participant.explain, /weighted by the days/);
});

test("the level of a result: first valid candidate, else episode (pre-phase-D results)", () => {
  assert.equal(resultLevel("participant", "episode"), "participant");
  assert.equal(resultLevel(undefined, "participant"), "participant");
  assert.equal(resultLevel(null, "patient"), "episode");
  assert.equal(resultLevel(), "episode");
});

test("nouns and counts", () => {
  assert.equal(unitNoun("participant", 1), "participant");
  assert.equal(unitNoun("participant", 2), "participants");
  assert.equal(unitNoun("episode", 1), "location episode");
  assert.equal(countLabel("episode", 1234), "1,234 location episodes");
  assert.equal(countLabel("participant", 0), "0 participants");
});

test("map rule: participant level asks the cohort, episode level the result", () => {
  // Participant level: result.csv has only pid + exposures; the cohort decides.
  assert.equal(hasStateColumn("participant", ["pid", "ndi"], ["pid", "state_fips"]), true);
  assert.equal(hasStateColumn("participant", ["pid", "ndi"], ["pid", "startDate"]), false);
  assert.equal(hasStateColumn("participant", ["pid", "ndi"], null), true); // unknown: try
  // Episode level: the result rows carry the cohort's columns.
  assert.equal(hasStateColumn("episode", ["pid", "state_fips", "ndi"], ["pid"]), true);
  assert.equal(hasStateColumn("episode", ["pid", "ndi"], ["pid", "state_fips"]), false);
  assert.equal(hasStateColumn("episode", undefined, undefined), true);
});

test("linkage rate is the share of output rows with a value", () => {
  assert.equal(linkageRate({ non_null: 3, null_count: 1 }), 0.75);
  assert.equal(linkageRate({ non_null: 0, null_count: 0 }), null);
});
