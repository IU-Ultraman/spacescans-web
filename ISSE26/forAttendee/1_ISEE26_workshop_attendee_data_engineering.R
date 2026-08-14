# 1_ISEE26_workshop_attendee_data_engineering.R
# Purpose:
#   Import the attendee-ready simulated dataset, read the SPACESCANS-linked
#   exposome parquet files, merge all linked measures by PATID, and save one
#   analysis-ready RDS for the workshop ExWAS and prediction exercises.

rm(list = ls())

# -----------------------------------------------------------------------------
# Package check
# -----------------------------------------------------------------------------
required_packages <- c("arrow", "dplyr", "purrr")
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
  library(arrow)
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

# Directory containing the SPACESCANS-linked parquet outputs.
linked_exposome_dir <- file.path(project_dir, "parquet")

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

# ZBP is used first for social-capital measures and CBP is used when ZBP is
# missing, matching the internal data-engineering workflow.
zbp_relative_path <- "1_county_zcta5_zbp_cbp/zbp_demo100k.parquet"
cbp_relative_path <- "1_county_zcta5_zbp_cbp/cbp_demo100k.parquet"

# Other linked files. Add, remove, or edit rows when the Codespaces directory
# layout changes. prefix is added after names are converted to snake_case.
linked_file_specs <- data.frame(
  source = c(
    "noise_270m",
    "tiger_road_proximity",
    "block_group_ndi",
    "block_group_walkability",
    "nhd_blue_space_proximity",
    "visible_nighttime_light",
    "temis_uv",
    "tract_fara_food_access"
  ),
  relative_path = c(
    "2_noise/noise_270m_demo100k.parquet",
    "3_tiger/roadProximity_demo100k.parquet",
    "4_bg_ndi_wi/ndi_demo100k.parquet",
    "4_bg_ndi_wi/wi_demo100k.parquet",
    "5_nhd/nhd_demo100k.parquet",
    "6_vnl/vnl_demo100k.parquet",
    "7_temis/temis_270m_demo100k.parquet",
    "8_tract_fara/fara_demo100k.parquet"
  ),
  prefix = c(
    NA,
    "road_",
    NA,
    NA,
    "nhd_",
    "vnl_",
    "temis_",
    "fara_"
  ),
  stringsAsFactors = FALSE
)

# Usually FALSE: retain only the coalesced social-capital measures.
keep_zbp_cbp_components <- FALSE
keep_zbp_cbp_source_flags <- FALSE

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

read_linked_parquet <- function(relative_path, prefix = NULL, source_name) {
  file <- file.path(linked_exposome_dir, relative_path)

  if (!file.exists(file)) {
    stop("Missing linked parquet file for ", source_name, ": ", file)
  }

  dat <- arrow::read_parquet(file) |>
    as.data.frame() |>
    standardize_id() |>
    clean_exposure_names(prefix = prefix)

  validate_unique_ids(dat, source_name)
  dat
}

make_manifest <- function(dat, source, relative_path) {
  data.frame(
    variable = setdiff(names(dat), "PATID"),
    source = source,
    relative_path = relative_path,
    stringsAsFactors = FALSE
  )
}

make_social_capital_table <- function() {
  zbp <- read_linked_parquet(
    relative_path = zbp_relative_path,
    prefix = NULL,
    source_name = "zbp_social_capital"
  )
  cbp <- read_linked_parquet(
    relative_path = cbp_relative_path,
    prefix = NULL,
    source_name = "cbp_social_capital"
  )

  zbp_vars <- setdiff(names(zbp), "PATID")
  cbp_vars <- setdiff(names(cbp), "PATID")
  social_vars <- union(zbp_vars, cbp_vars)

  zbp_renamed <- zbp
  cbp_renamed <- cbp
  names(zbp_renamed)[match(zbp_vars, names(zbp_renamed))] <- paste0(zbp_vars, "_zbp")
  names(cbp_renamed)[match(cbp_vars, names(cbp_renamed))] <- paste0(cbp_vars, "_cbp")

  both <- full_join(zbp_renamed, cbp_renamed, by = "PATID")
  out <- both["PATID"]

  for (v in social_vars) {
    zbp_v <- paste0(v, "_zbp")
    cbp_v <- paste0(v, "_cbp")

    if (zbp_v %in% names(both) && cbp_v %in% names(both)) {
      out[[paste0("soc_", v)]] <- dplyr::coalesce(
        both[[zbp_v]],
        both[[cbp_v]]
      )
    } else if (zbp_v %in% names(both)) {
      out[[paste0("soc_", v)]] <- both[[zbp_v]]
    } else {
      out[[paste0("soc_", v)]] <- both[[cbp_v]]
    }
  }

  if (isTRUE(keep_zbp_cbp_source_flags)) {
    zbp_cols <- intersect(paste0(social_vars, "_zbp"), names(both))
    cbp_cols <- intersect(paste0(social_vars, "_cbp"), names(both))

    out$soc_zbp_nonmissing_n <- if (length(zbp_cols) > 0) {
      rowSums(!is.na(both[zbp_cols]))
    } else {
      0L
    }
    out$soc_cbp_nonmissing_n <- if (length(cbp_cols) > 0) {
      rowSums(!is.na(both[cbp_cols]))
    } else {
      0L
    }
    out$soc_source_rule <- case_when(
      out$soc_zbp_nonmissing_n > 0 ~ "zbp_primary",
      out$soc_cbp_nonmissing_n > 0 ~ "cbp_fallback",
      TRUE ~ NA_character_
    )
  }

  if (isTRUE(keep_zbp_cbp_components)) {
    raw_components <- both[setdiff(names(both), "PATID")]
    names(raw_components) <- paste0("soc_raw_", names(raw_components))
    out <- bind_cols(out, raw_components)
  }

  validate_unique_ids(out, "coalesced_social_capital")
  out
}

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

if (!dir.exists(linked_exposome_dir)) {
  stop("linked_exposome_dir does not exist: ", linked_exposome_dir)
}

message("Reading and coalescing ZBP/CBP social-capital files...")
social <- make_social_capital_table()

message("Reading remaining linked exposome parquet files...")
other_tables <- lapply(seq_len(nrow(linked_file_specs)), function(i) {
  spec <- linked_file_specs[i, ]
  read_linked_parquet(
    relative_path = spec$relative_path,
    prefix = spec$prefix,
    source_name = spec$source
  )
})
names(other_tables) <- linked_file_specs$source

exposure_tables <- c(
  list(zbp_primary_cbp_fallback = social),
  other_tables
)

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
    ". Edit linked_file_specs prefixes before merging."
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

social_manifest <- make_manifest(
  social,
  source = "zbp_primary_cbp_fallback",
  relative_path = paste(zbp_relative_path, cbp_relative_path, sep = " | ")
)

other_manifests <- lapply(seq_along(other_tables), function(i) {
  make_manifest(
    other_tables[[i]],
    source = linked_file_specs$source[i],
    relative_path = linked_file_specs$relative_path[i]
  )
})

exposure_manifest <- bind_rows(c(list(social_manifest), other_manifests)) |>
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

saveRDS(analytic, merged_rds_file)
write.csv(exposure_manifest, manifest_csv, row.names = FALSE)
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
