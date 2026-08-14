# ISEE 2026 workshop — analysis scripts

Three R scripts that take a SPACESCANS linkage and carry it through to an
exposome-wide association study and a prediction model. Run them in order;
each reads what the previous one wrote.

Open **RStudio on port 8787**, then in its Terminal:

```bash
cd ~/ISEE26Workshop/forAttendee
Rscript 1_ISEE26_workshop_attendee_data_engineering.R
Rscript 2_ISEE26_workshop_attendee_exwas.R
Rscript 3_ISEE26_workshop_attendee_prediction.R
```

## Before you start

Link your cohort in the SPACESCANS web app (port 3000) and let it finish.
Nothing needs downloading: script 1 finds the most recent run under
`/home/rstudio/spacescans-runs/tasks/`, which is the app's output mounted
read-only into this container.

To analyse an earlier run instead, set `spacescans_result_csv` near the top of
script 1 to that run's `output/result.csv`.

## What each script does

**1 — Data engineering.** Joins the linked exposures onto the attendee cohort
by `PATID`, one row per patient. Writes `1_DataEngineering/`: the merged
dataset (`.rds`) that the other two scripts read, an exposure manifest,
`feature_labels.csv` (human-readable names, taken from the app's feature
dictionary), and QC tables for linkage coverage and missingness.

Exposome sources absent from your run are skipped with a message — running
three variables instead of six needs no edits.

**2 — ExWAS.** Exposure QC, correlation pruning, one full-sample MICE
imputation, then covariate-adjusted single-exposure logistic models in
independent 50% discovery and replication samples with Bonferroni correction;
exposures significant in both go into one multi-exposure model. Writes
`2_ExWAS/`: 14 tables, volcano plots, and the fitted objects.

**3 — Prediction.** Elastic net and CatBoost on a 70/30 split, each tuned by
cross-validated AUROC, compared on the held-out 30% by AUROC, AUPRC, Brier
score and calibration, with SHAP contributions for the top exposures. Writes
`3_Prediction/`: tables, figures, both models, and per-patient predictions.

## Settings

Each script has a `USER SETTINGS` block at the top — paths, the outcome and
covariates, QC thresholds, seeds, and model grids. Everything else below it is
the analysis itself.

Result tables carry `exposure_label` beside each variable name; the longer
description for every variable is in `1_DataEngineering/feature_labels.csv`.
