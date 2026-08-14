# 1_ISEE26_workshop_attendee_data_engineering.R
# Purpose:
#   Import the attendee-ready simulated dataset, read the linked dataset that
#   the SPACESCANS web app produces (output/result.csv), merge all linked
#   measures by PATID, and save one analysis-ready RDS for the workshop ExWAS
#   and prediction exercises.

rm(list = ls())

# -----------------------------------------------------------------------------
# Package check
# -----------------------------------------------------------------------------
# arrow is no longer needed: the linked data arrives as one CSV.
required_packages <- c("dplyr", "purrr")
missing_packages <- required_packages[
  !vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)
]

if (length(missing_packages) > 0) {
  stop(
    "Install the following packages before running this script: ",
    paste(missing_packages, collapse = ", "),
    "\nFor example: install.packages(c(",
    paste(sprintf('"%s"', missing_packages), collapse = ", "),
    "))"
  )
}

suppressPackageStartupMessages({
  library(dplyr)
  library(purrr)
})

# =============================================================================
# USER SETTINGS: edit paths and options here
# =============================================================================

# Workshop directory. In the SPACESCANS container this is where
# docker-compose mounts the repository's ISSE26/ folder; the original
# authoring path is kept for reference.
#   internal: "/mnt/md0/Research Project/SPACESCANS/data/ISEE26Workshop"
project_dir <- "/home/rstudio/ISEE26Workshop"

# Scripts live in forAttendee/; the simulated cohort ships beside it.
attendee_dir <- file.path(project_dir, "forAttendee")
data_dir <- file.path(project_dir, "demoDataWithCovariates")
attendee_input_file <- file.path(
  data_dir,
  "ISEE26_workshop_attendee_linkage_input_100000.rds"
)

# The linked dataset downloaded from the SPACESCANS web app: one wide CSV,
# one row per cohort row, cohort columns first and then one column per
# exposure measure. Replaces the per-source parquet directory this script
# used to read.
spacescans_result_csv <- file.path(data_dir, "result.csv")

# Companion file the app writes beside result.csv, describing each exposure
# column. Optional: without it the later scripts fall back to raw variable
# names in their tables and figures.
spacescans_dictionary_csv <- file.path(data_dir, "feature_dictionary.csv")

# Output directory and primary output file for this script.
output_dir <- file.path(attendee_dir, "1_DataEngineering")
merged_rds_file <- file.path(
  output_dir,
  "ISEE26_workshop_merged_exposome.rds"
)

# The RDS is always written. Set TRUE only if a large merged CSV is also useful.
write_merged_csv <- FALSE
merged_csv_file <- file.path(
  output_dir,
  "ISEE26_workshop_merged_exposome.csv"
)

# Which columns of result.csv belong to which exposome source.
#
# The per-source parquet files carried this grouping in their file names; a
# single flat CSV does not, so it is declared here. Column names are exactly
# as SPACESCANS writes them (see the run's feature_dictionary.csv, or
# backend/app/data/variable_metadata.json in the app repo); `prefix` and the
# `source` labels are unchanged from the parquet era, so the merged variable
# names and every downstream lookup keyed on source still match.
#
# Bluespace, night-time lights and TEMIS UV are absent on purpose: their
# inputs are 50 GB, account-gated, and 29 GB-plus-not-redistributable
# respectively, none of which fits a Codespace. Add a row back if you run one
# of them on hardware that can hold it.
spacescans_specs <- list(
  list(
    source = "zbp_primary_cbp_fallback",
    prefix = "soc_",
    columns = c(
      "r_religious", "r_civic", "r_business", "r_political", "r_professional",
      "r_labor", "r_bowling", "r_recreational", "r_golf", "r_sports"
    )
  ),
  list(
    source = "noise_270m",
    prefix = NA,
    columns = c("l50dba_exi", "l50dba_imp", "l50dba_nat")
  ),
  list(
    source = "tiger_road_proximity",
    prefix = "road_",
    columns = c("dist_pri", "dist_sec", "dist_prisec")
  ),
  list(
    source = "block_group_ndi",
    prefix = NA,
    columns = c("ndi")
  ),
  list(
    source = "block_group_walkability",
    prefix = NA,
    columns = c("NatWalkInd")
  ),
  list(
    source = "tract_fara_food_access",
    prefix = "fara_",
    columns = c("LILATracts_1And10", "LATracts1", "HUNVFlag", "LowIncomeTracts")
  )
)

# Warn when a linked source contains records for fewer than this proportion of
# attendee PATIDs. Missing exposure values can still occur within linked rows.
minimum_expected_linkage_coverage <- 0.90

# =============================================================================
# Helper functions
# =============================================================================

clean_name_one <- function(x) {
  x <- gsub("([a-z0-9])([A-Z])", "\\1_\\2", x)
  x <- gsub("[^A-Za-z0-9]+", "_", x)
  x <- gsub("_+", "_", x)
  x <- gsub("^_|_$", "", x)
  tolower(x)
}

standardize_id <- function(dat) {
  id_candidates <- names(dat)[tolower(names(dat)) %in% c("patid", "pid")]

  if (length(id_candidates) == 0) {
    stop("Could not find an ID column named PATID or pid.")
  }
  if (length(id_candidates) > 1) {
    stop(
      "Found more than one possible participant-ID column: ",
      paste(id_candidates, collapse = ", ")
    )
  }

  names(dat)[names(dat) == id_candidates] <- "PATID"
  dat$PATID <- as.character(dat$PATID)
  dat
}

clean_exposure_names <- function(dat, prefix = NULL) {
  exposure_cols <- setdiff(names(dat), "PATID")
  new_names <- vapply(exposure_cols, clean_name_one, character(1))

  if (!is.null(prefix) && !is.na(prefix) && nzchar(prefix)) {
    new_names <- paste0(prefix, new_names)
  }

  names(dat)[match(exposure_cols, names(dat))] <- new_names

  if (anyDuplicated(names(dat))) {
    duplicated_names <- unique(names(dat)[duplicated(names(dat))])
    stop(
      "Duplicate variable names were created while cleaning a linked file: ",
      paste(duplicated_names, collapse = ", ")
    )
  }

  dat
}

validate_unique_ids <- function(dat, source_name) {
  if (anyNA(dat$PATID) || any(dat$PATID == "")) {
    stop(source_name, " contains missing or blank PATID values.")
  }

  n_duplicate <- sum(duplicated(dat$PATID))
  if (n_duplicate > 0) {
    stop(
      source_name,
      " contains duplicate PATID values; duplicate rows = ",
      n_duplicate
    )
  }

  invisible(TRUE)
}

read_attendee_data <- function(file) {
  if (!file.exists(file)) {
    stop("Attendee input file does not exist: ", file)
  }

  if (grepl("\\.rds$", file, ignore.case = TRUE)) {
    dat <- readRDS(file)

    if (inherits(dat, "sf")) {
      if (!requireNamespace("sf", quietly = TRUE)) {
        stop("Package 'sf' is required to read an sf-formatted attendee RDS.")
      }
      dat <- sf::st_drop_geometry(dat)
    }

    dat <- as.data.frame(dat)
  } else if (grepl("\\.csv$", file, ignore.case = TRUE)) {
    dat <- read.csv(
      file,
      stringsAsFactors = FALSE,
      check.names = FALSE,
      colClasses = c(
        PATID = "character",
        state_fips = "character",
        county_fips = "character",
        tract_geoid = "character",
        bg_geoid = "character"
      )
    )
  } else {
    stop("attendee_input_file must be an .rds or .csv file: ", file)
  }

  dat <- standardize_id(dat)

  for (v in intersect(c("startDate", "endDate"), names(dat))) {
    dat[[v]] <- as.Date(dat[[v]])
  }

  dat
}

read_spacescans_result <- function(file) {
  if (!file.exists(file)) {
    stop(
      "SPACESCANS result file not found: ", file, "\n",
      "  Run the linkage in the web app, then copy output/result.csv here ",
      "(inside the workshop container it is also readable under ",
      "/home/rstudio/spacescans-runs/tasks/<task-id>/output/)."
    )
  }

  # Identifier and FIPS columns must stay character: read.csv would turn "01"
  # into 1 and an 11-digit tract GEOID into 2.7e10. colClasses errors on a
  # name that is not present, so the header decides which ones to declare.
  header <- names(read.csv(file, nrows = 0, check.names = FALSE))
  as_character <- intersect(
    c("pid", "PATID", "state_fips", "county_fips", "tract_geoid", "bg_geoid"),
    header
  )
  col_classes <- setNames(rep("character", length(as_character)), as_character)

  dat <- read.csv(
    file,
    stringsAsFactors = FALSE,
    check.names = FALSE,
    colClasses = col_classes
  ) |>
    standardize_id()

  validate_unique_ids(dat, "spacescans_result")
  dat
}

# Split the wide result into the per-source tables the rest of this script
# expects, applying each source's prefix exactly as the parquet reader did —
# so merged variable names are unchanged from the parquet era.
#
# A source whose columns are entirely absent is skipped with a message rather
# than an error: a run covers only the exposomes that were selected in the app,
# and a workshop that drops one should not have to edit this file.
split_result_by_source <- function(result_dat, specs) {
  tables <- list()

  for (spec in specs) {
    present <- intersect(spec$columns, names(result_dat))
    missing <- setdiff(spec$columns, names(result_dat))

    if (length(present) == 0) {
      message(
        "  - ", spec$source, ": not present in result.csv, skipping ",
        "(expected columns: ", paste(spec$columns, collapse = ", "), ")"
      )
      next
    }
    if (length(missing) > 0) {
      warning(
        spec$source, " is missing ", length(missing), " expected column(s): ",
        paste(missing, collapse = ", "),
        call. = FALSE
      )
    }

    tbl <- result_dat[, c("PATID", present), drop = FALSE] |>
      clean_exposure_names(prefix = spec$prefix)
    validate_unique_ids(tbl, spec$source)

    message("  - ", spec$source, ": ", length(present), " measure(s)")
    tables[[spec$source]] <- tbl
  }

  if (length(tables) == 0) {
    stop(
      "None of the expected exposome columns were found in ", basename(spacescans_result_csv),
      ". Was the linkage run with any exposures selected?"
    )
  }

  tables
}

make_manifest <- function(dat, source, relative_path) {
  data.frame(
    variable = setdiff(names(dat), "PATID"),
    source = source,
    relative_path = relative_path,
    stringsAsFactors = FALSE
  )
}

# The ZBP-primary / CBP-fallback coalescing that used to live here now happens
# inside the SPACESCANS pipeline, which emits one already-resolved set of
# community-organization measures. The source label is kept as
# "zbp_primary_cbp_fallback" so downstream category lookups still match.

linkage_coverage_one <- function(linked_dat, source_name, attendee_ids) {
  n_attendee <- length(attendee_ids)
  n_linked <- dplyr::n_distinct(linked_dat$PATID)
  n_matched <- sum(attendee_ids %in% linked_dat$PATID)

  data.frame(
    source = source_name,
    n_attendee_PATID = n_attendee,
    n_linked_PATID = n_linked,
    n_attendee_with_linked_record = n_matched,
    attendee_linkage_coverage_pct = 100 * n_matched / n_attendee,
    n_linked_PATID_not_in_attendee = sum(!linked_dat$PATID %in% attendee_ids),
    stringsAsFactors = FALSE
  )
}

# =============================================================================
# 1) Import and validate the attendee-ready dataset
# =============================================================================

dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

message("Reading attendee input: ", attendee_input_file)
attendee_dat <- read_attendee_data(attendee_input_file)

required_attendee_vars <- c(
  "PATID",
  "binary_outcome",
  "age",
  "sex",
  "sex_label",
  "race_eth",
  "race_eth_label",
  "startDate",
  "endDate",
  "longitude",
  "latitude",
  "state_fips",
  "county_fips",
  "tract_geoid",
  "bg_geoid"
)

missing_attendee_vars <- setdiff(required_attendee_vars, names(attendee_dat))
if (length(missing_attendee_vars) > 0) {
  stop(
    "The attendee dataset is missing required variables: ",
    paste(missing_attendee_vars, collapse = ", ")
  )
}

validate_unique_ids(attendee_dat, "attendee dataset")

outcome_values <- sort(unique(attendee_dat$binary_outcome[!is.na(attendee_dat$binary_outcome)]))
if (!all(outcome_values %in% c(0, 1)) || length(outcome_values) != 2) {
  stop(
    "binary_outcome must contain both 0 and 1. Observed non-missing values: ",
    paste(outcome_values, collapse = ", ")
  )
}

attendee_dat$.attendee_row_order <- seq_len(nrow(attendee_dat))
attendee_ids <- attendee_dat$PATID

# =============================================================================
# 2) Read all linked exposome files
# =============================================================================

message("Reading the SPACESCANS linked dataset: ", spacescans_result_csv)
spacescans_result <- read_spacescans_result(spacescans_result_csv)
message(
  "  ", nrow(spacescans_result), " rows, ",
  ncol(spacescans_result), " columns"
)

message("Splitting it into exposome sources...")
exposure_tables <- split_result_by_source(spacescans_result, spacescans_specs)

# Stop before joining if two sources would create the same exposure name.
exposure_name_registry <- unlist(
  lapply(exposure_tables, function(x) setdiff(names(x), "PATID")),
  use.names = FALSE
)
duplicated_exposure_names <- unique(
  exposure_name_registry[duplicated(exposure_name_registry)]
)

if (length(duplicated_exposure_names) > 0) {
  stop(
    "Exposure names overlap across linked sources: ",
    paste(duplicated_exposure_names, collapse = ", "),
    ". Edit the prefixes in spacescans_specs before merging."
  )
}

attendee_overlap <- intersect(exposure_name_registry, names(attendee_dat))
if (length(attendee_overlap) > 0) {
  stop(
    "Linked exposure names overlap with attendee variables: ",
    paste(attendee_overlap, collapse = ", ")
  )
}

# =============================================================================
# 3) Build manifests and linkage-coverage diagnostics
# =============================================================================

# Same two required columns (variable, source) as before, so scripts 2 and 3
# consume this unchanged; relative_path now names the one file everything
# came from.
manifests <- lapply(names(exposure_tables), function(source_name) {
  make_manifest(
    exposure_tables[[source_name]],
    source = source_name,
    relative_path = basename(spacescans_result_csv)
  )
})

exposure_manifest <- bind_rows(manifests) |>
  distinct(variable, .keep_all = TRUE) |>
  arrange(source, variable)

linkage_coverage <- bind_rows(lapply(names(exposure_tables), function(source_name) {
  linkage_coverage_one(
    linked_dat = exposure_tables[[source_name]],
    source_name = source_name,
    attendee_ids = attendee_ids
  )
}))

low_coverage <- linkage_coverage |>
  filter(attendee_linkage_coverage_pct < 100 * minimum_expected_linkage_coverage)

if (nrow(low_coverage) > 0) {
  warning(
    "Linked-record coverage was below ",
    100 * minimum_expected_linkage_coverage,
    "% for: ",
    paste(low_coverage$source, collapse = ", ")
  )
}

# =============================================================================
# 4) Merge linked exposures onto attendees and run QC
# =============================================================================

message("Merging linked exposure tables onto attendee records by PATID...")
analytic <- purrr::reduce(
  exposure_tables,
  .init = attendee_dat,
  .f = function(x, y) left_join(x, y, by = "PATID")
) |>
  arrange(.attendee_row_order) |>
  select(-.attendee_row_order)

if (nrow(analytic) != nrow(attendee_dat)) {
  stop(
    "The merge changed the number of attendee rows from ",
    nrow(attendee_dat),
    " to ",
    nrow(analytic),
    ". Check linked files for duplicate PATID values."
  )
}

if (!identical(analytic$PATID, attendee_ids)) {
  stop("The merge changed attendee PATID order.")
}

exposure_vars <- exposure_manifest$variable
missing_from_merged <- setdiff(exposure_vars, names(analytic))
if (length(missing_from_merged) > 0) {
  stop(
    "Manifest variables missing from the merged dataset: ",
    paste(missing_from_merged, collapse = ", ")
  )
}

exposure_missingness <- data.frame(
  variable = exposure_vars,
  class = vapply(
    analytic[exposure_vars],
    function(x) paste(class(x), collapse = "/"),
    character(1)
  ),
  missing_n = vapply(analytic[exposure_vars], function(x) sum(is.na(x)), integer(1)),
  missing_pct = vapply(
    analytic[exposure_vars],
    function(x) 100 * mean(is.na(x)),
    numeric(1)
  ),
  stringsAsFactors = FALSE
) |>
  left_join(exposure_manifest, by = "variable") |>
  arrange(desc(missing_pct), source, variable)

data_engineering_qc <- data.frame(
  metric = c(
    "n_rows",
    "n_unique_PATID",
    "n_columns",
    "n_linked_exposure_variables",
    "n_binary_outcome_cases",
    "binary_outcome_prevalence"
  ),
  value = c(
    nrow(analytic),
    dplyr::n_distinct(analytic$PATID),
    ncol(analytic),
    length(exposure_vars),
    sum(analytic$binary_outcome == 1, na.rm = TRUE),
    mean(analytic$binary_outcome == 1, na.rm = TRUE)
  ),
  stringsAsFactors = FALSE
)

# =============================================================================
# 5) Save analysis-ready data and QC outputs
# =============================================================================

manifest_csv <- file.path(output_dir, "exposure_variable_manifest.csv")
coverage_csv <- file.path(output_dir, "linkage_coverage_by_source.csv")
missingness_csv <- file.path(output_dir, "exposure_missingness.csv")
qc_csv <- file.path(output_dir, "data_engineering_qc.csv")
labels_csv <- file.path(output_dir, "feature_labels.csv")

# Translate the app's dictionary into labels keyed by the names this script
# produced. The dictionary is keyed on raw SPACESCANS columns (dist_pri),
# while the merged data uses the cleaned, prefixed forms (road_dist_pri), so
# a direct join would match nothing. Doing the translation here — the one
# place that owns the renaming — keeps scripts 2 and 3 free of it.
write_feature_labels <- function(dictionary_csv, specs, out_csv) {
  if (!file.exists(dictionary_csv)) {
    message(
      "No feature dictionary at ", dictionary_csv,
      " — later scripts will label figures with raw variable names."
    )
    return(invisible(NULL))
  }

  dict <- read.csv(dictionary_csv, stringsAsFactors = FALSE, check.names = FALSE)
  if (!all(c("feature_name", "short_description") %in% names(dict))) {
    warning(
      "Feature dictionary lacks feature_name/short_description; skipping labels.",
      call. = FALSE
    )
    return(invisible(NULL))
  }

  rows <- lapply(specs, function(spec) {
    keep <- dict[dict$feature_name %in% spec$columns, , drop = FALSE]
    if (nrow(keep) == 0) return(NULL)
    varname <- vapply(keep$feature_name, clean_name_one, character(1))
    if (!is.null(spec$prefix) && !is.na(spec$prefix) && nzchar(spec$prefix)) {
      varname <- paste0(spec$prefix, varname)
    }
    data.frame(
      varname = unname(varname),
      label = keep$short_description,
      description = if ("detailed_description" %in% names(keep)) {
        keep$detailed_description
      } else {
        keep$short_description
      },
      stringsAsFactors = FALSE
    )
  })

  labels <- bind_rows(rows)
  if (nrow(labels) == 0) {
    warning("Feature dictionary matched none of the linked columns.", call. = FALSE)
    return(invisible(NULL))
  }

  write.csv(labels, out_csv, row.names = FALSE)
  message("Saved feature labels: ", out_csv, " (", nrow(labels), " variables)")
  invisible(labels)
}

saveRDS(analytic, merged_rds_file)
write.csv(exposure_manifest, manifest_csv, row.names = FALSE)
write_feature_labels(spacescans_dictionary_csv, spacescans_specs, labels_csv)
write.csv(linkage_coverage, coverage_csv, row.names = FALSE)
write.csv(exposure_missingness, missingness_csv, row.names = FALSE)
write.csv(data_engineering_qc, qc_csv, row.names = FALSE)

if (isTRUE(write_merged_csv)) {
  write.csv(analytic, merged_csv_file, row.names = FALSE)
}

message("Saved merged analysis RDS: ", merged_rds_file)
if (isTRUE(write_merged_csv)) message("Saved merged analysis CSV: ", merged_csv_file)
message("Saved exposure manifest: ", manifest_csv)
message("Saved linkage coverage: ", coverage_csv)
message("Saved exposure missingness: ", missingness_csv)
message("Saved data-engineering QC: ", qc_csv)

print(data_engineering_qc)
print(linkage_coverage)
