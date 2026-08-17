# ISEE 2026 workshop — analysis scripts

Two tracks, ending in the same ExWAS and prediction model. They differ only in
where the linked exposures come from. Open **RStudio on port 8787**, then in its
Terminal:

```bash
cd ~/ISEE26Workshop/forAttendee
```

## Track A — link a cohort yourself (10,000 patients)

```bash
Rscript 1_ISEE26_workshop_attendee_data_engineering.R
Rscript 2_ISEE26_workshop_attendee_exwas.R
Rscript 3_ISEE26_workshop_attendee_prediction.R
```

First link the cohort in the SPACESCANS web app (port 3000) and let it finish —
upload `demoDataWithCovariates/ISEE26_workshop_linkage_minimal_10000.csv`.
Nothing needs downloading afterwards: the app's output is mounted read-only into
this container, one directory per run, named for its task id —

```text
/home/rstudio/spacescans-runs/tasks/task-877c06ae-383b-48ff-94ae-bd79e46e2cb7/
```

and script 1 **automatically** picks the most recent one.

## Track B — pre-linked dataset (100,000 patients)

```bash
Rscript 2_ISEE26_workshop_attendee_exwas_100k.R
Rscript 3_ISEE26_workshop_attendee_prediction_100k.R
```

No app run and no script 1: the linkage was done ahead of time and ships in
`prelinked_100k/1_DataEngineering/`, with 72 exposures across nine sources.
Results are written beside it in `prelinked_100k/`.

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
