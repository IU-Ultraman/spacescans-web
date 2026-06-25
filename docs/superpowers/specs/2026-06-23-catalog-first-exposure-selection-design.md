# Catalog-First Exposure Selection (Wizard Reorder) — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorming complete)
**Scope owner:** spacescans-web (frontend only)

## Goal

把新建任务向导**翻转入口**:让用户**先**在一个"只显示能链到 pipeline 的暴露"的 catalog 风格界面上选择暴露,**再**上传数据。覆盖率预检随之从选择步搬到 Review 步(那里才有数据)。目标人群 persona (a)(懂科研、不懂本工具的研究者)先看懂"有哪些暴露、各是什么意思",再开始干活。

这是"易懂性"初衷的子项;**纯前端改动**(后端/pipeline/coverage 接口不动)。

## Background / 现状

- 当前向导(`frontend/src/app/dashboard/task/new/page.tsx`):`step0 Upload → step1 Buffer → step2 Variables → step3 Review`。
  - `UploadStep` 在上传时 `api.createTask()` 创建任务并拿到 `taskId`。
  - `VariablesStep`(step2)按**边界**(`groupByBoundary`)分组渲染 `VariableCard`,每张卡勾选后用 `taskId` 拉覆盖率(`VariableCoveragePanel`)。
  - `ReviewStep`(step3)汇总后 `saveConfig + startTask`。
- `VariableCard` 当前必传 `taskId`,勾选即渲染 `VariableCoveragePanel`。
- `variable-grouping.ts` 有 `groupByBoundary` + `BOUNDARY_ORDER/BOUNDARY_LABEL`(显式常量风格);`frontend/scripts/check-variable-grouping.mjs` 是其 smoke。
- `WizardLayout` 的 `STEPS` 常量定义 4 个步骤标签。
- 9 个变量已带 `ontology_id`(前序子项),其链接节点的父节点即"环境域"。

## 已锁定决策

1. catalog 风格选择面作为**第 1 步**,选择结果带进任务(Q1=A)。
2. 新流程 `Select Exposures → Upload → Buffer → Review`;**覆盖率预检移到 Review**(Q2=A)。
3. 选择面用**按本体域分组的卡片**(复用 `VariableCard`),非剪枝树;独立 `/catalog` 全本体页**保持不动**(Q3=A)。
4. 域分组放**前端**(本特性纯前端);不新增后端 metadata 字段。

## 设计

### A. 域分组(`frontend/src/lib/variable-grouping.ts`)

新增,镜像现有 `groupByBoundary` 风格:

```typescript
export const DOMAIN_ORDER = ['built', 'natural', 'social'] as const;
export type DomainKey = typeof DOMAIN_ORDER[number];

export const DOMAIN_LABEL: Record<DomainKey, string> = {
  built: 'Built Environment',
  natural: 'Natural Environment',
  social: 'Social Environment',
};

// Each variable's environmental domain = its linked ontology node's parent
// (Built/Natural/Social Environment Exposome). Kept as an explicit map here
// because domain is a presentation concern; a new variable must be added here
// too (groupByDomain routes anything unmapped to an "Other" bucket so it is
// never silently dropped, and check-variable-grouping.mjs asserts completeness).
export const VARIABLE_DOMAIN: Record<string, DomainKey> = {
  walkability: 'built',
  tiger_proximity: 'built',
  fara_tract: 'built',
  noise: 'natural',
  vnl: 'natural',
  temis: 'natural',
  nhd_bluespace: 'natural',
  ndi: 'social',
  cbp_zcta5: 'social',
};
```

`groupByDomain(variables)` returns `Partial<Record<DomainKey | 'other', [string, VariableMetadata][]>>`: iterate `DOMAIN_ORDER`, collect entries whose key maps to that domain; any key absent from `VARIABLE_DOMAIN` goes into a trailing `other` group (only included if non-empty). Mirror the `groupByBoundary` shape so the step component swaps grouping with minimal change.

### B. `VariableCard` — make coverage optional (`variable-card.tsx`)

Make `taskId` optional and only render the coverage panel when a `taskId` is provided:

```tsx
interface VariableCardProps {
  varKey: string;
  meta: VariableMetadata;
  checked: boolean;
  onToggle: () => void;
  taskId?: string;   // omitted in the Select-Exposures step (no task/data yet)
}
// ...
{checked && taskId && (
  <VariableCoveragePanel taskId={taskId} variableKey={varKey} />
)}
```

Everything else on the card (label, description, chips, "View in ontology" link) is unchanged, so the card works identically with or without a task.

### C. Select Exposures step (rework `variables-step.tsx`)

This becomes wizard **step 0**. Changes:
- Drop the `taskId` prop (no coverage here). Props: `{ onComplete, onBack, initialSelection }`. Add `onBack` (step 0 currently has none; now it is reachable as step 1's "Back" target — see E — but step 0 itself needs no Back; keep `onBack` optional and omit the Back button when not provided).
- Group with `groupByDomain` (+ `DOMAIN_ORDER`/`DOMAIN_LABEL`) instead of `groupByBoundary`. Section headers show the domain label; within a section, an unmapped `other` group (if any) renders last under an "Other" header.
- Render `VariableCard` **without** `taskId` (no coverage).
- Update copy: card title "Select Exposures"; description e.g. "Browse the exposures you can link — grouped by environmental domain. Pick one or more, then upload your cohort." Keep `canContinue = selected.length >= 1` and the "Next" button.
- The component keeps the name `VariablesStep` (still selects variables); only grouping, copy, and the dropped `taskId`/coverage change.

### D. Coverage moves to Review (`review-step.tsx`)

Add a "Cohort Coverage" `SummarySection` (after the Variables section) that, for each selected variable, renders the existing `VariableCoveragePanel` (it already takes `taskId` + `variableKey` and fetches `api.getCoverage`). Prefix each panel with the variable's label (from `catalog.variables[key]?.label ?? key`). `taskId` is available at Review. Add a one-line hint: "Coverage reflects how much of your uploaded cohort each exposure can cover; adjust your selection in step 1 if it's low." No backend change — reuses the existing coverage endpoint/component.

### E. Reorder the wizard (`new/page.tsx` + `wizard-layout.tsx`)

New step order and wiring in `NewTaskPage`:

| step | component | onComplete → | onBack → |
| --- | --- | --- | --- |
| 0 | `VariablesStep` (exposures) | `setSelectedVariables(v); setStep(1)` | — (no Back on first step) |
| 1 | `UploadStep` | `setTaskId(id); setDataSummary(s); setStep(2)` | `setStep(0)` |
| 2 | `BufferStep` | `setBufferConfig(c); setStep(3)` | `setStep(1)` |
| 3 | `ReviewStep` | `saveConfig + startTask` | `setStep(2)` |

- `VariablesStep` (step 0) renders only when the catalog has loaded (it fetches its own catalog via `useVariableCatalog`); it no longer requires `taskId`. Gate step 3 render on `taskId && dataSummary && bufferConfig` (unchanged dependency, just later).
- `UploadStep` gains an optional `onBack` prop + a "Back" button (to return to exposures). To avoid creating duplicate orphan tasks when the user goes back and forward, `NewTaskPage` passes the already-created `taskId`/`dataSummary` back into `UploadStep` as `initialTaskId`/`initialSummary`; `UploadStep` initializes its internal `taskId`/`dataSummary` state from those props so a revisit shows the existing upload summary (and the "Next" button) instead of re-uploading. If the user picks a *new* file, it uploads to the existing `taskId` via `api.uploadFile(taskId, file)` (re-create only when no `taskId` yet).
- `WizardLayout.STEPS` reorder to:
  ```ts
  const STEPS = [
    { label: "Select Exposures", description: "Pick exposures" },
    { label: "Upload Data", description: "CSV file" },
    { label: "Buffer Settings", description: "Shape & size" },
    { label: "Review & Run", description: "Confirm & start" },
  ];
  ```

### F. Testing

- **Grouping unit/smoke** (`frontend/scripts/check-variable-grouping.mjs`): extend to import `groupByDomain`, `DOMAIN_ORDER`, `VARIABLE_DOMAIN`; assert (a) the 9 known variables map to expected domains, (b) `groupByDomain` returns groups in `DOMAIN_ORDER`, (c) an unknown-key variable lands in `other`. (This file runs against the tsc-emitted JS in `.next-check`, per its existing setup.)
- **Type check**: `cd frontend && tsc --noEmit` clean (the props/flow changes are the main guardrail).
- **Manual** (documented, not automated — consistent with this repo's wizard testing): start a task → step 1 shows exposures grouped by Built/Natural/Social with definitions + "View in ontology", no coverage; Upload → Buffer → Review shows per-exposure coverage; Back from Upload returns to exposures without creating a second task.

## Out of scope

- Backend / pipeline / coverage-endpoint changes (none).
- Changes to the standalone `/catalog` full-ontology browser or the Phase-2 "View in ontology" deep-link.
- A pruned-tree catalog (rejected in favor of grouped cards).
- Adding a `domain` field to `variable_metadata.json` (kept as a frontend constant).

## Files touched

- Modify `frontend/src/lib/variable-grouping.ts` (add domain grouping)
- Modify `frontend/scripts/check-variable-grouping.mjs` (domain smoke)
- Modify `frontend/src/components/wizard/variable-card.tsx` (optional `taskId`/coverage)
- Modify `frontend/src/components/wizard/variables-step.tsx` (domain grouping, drop `taskId`, copy)
- Modify `frontend/src/components/wizard/upload-step.tsx` (optional `onBack` + `initialTaskId`/`initialSummary`, re-upload to existing task)
- Modify `frontend/src/components/wizard/review-step.tsx` (coverage section)
- Modify `frontend/src/app/dashboard/task/new/page.tsx` (reorder steps + wiring)
- Modify `frontend/src/components/wizard/wizard-layout.tsx` (STEPS labels/order)
