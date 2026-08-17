# ---------------------------------------------------------------------------
# 100k variant. Identical analysis to 3_ISEE26_workshop_attendee_prediction.R; it
# reads the pre-linked 100,000-patient dataset that ships in
# prelinked_100k/ instead of the linkage you ran in the app, and writes its
# own outputs beside it.
#
# Why both exist: linking 100,000 patients takes far longer than a workshop
# session allows, but 10,000 leaves the downstream analyses underpowered. Run
# the 10k linkage yourself, then repeat the analysis at full size here.
# ---------------------------------------------------------------------------

# =============================================================================
# 3_ISEE26_workshop_attendee_prediction.R
# =============================================================================
# Purpose:
#   Develop and evaluate two binary-outcome prediction models using all
#   demographic covariates and all technically eligible linked exposures:
#
#     1. Elastic-net logistic regression
#     2. CatBoost
#
# Design:
#   - One shared stratified random 70% training / 30% testing split is created
#     once and used by both elastic net and CatBoost
#   - All preprocessing parameters learned from training data only
#   - Elastic net: five-fold cross-validation over an alpha grid; select the
#     alpha and lambda.min combination with the highest cross-validated AUROC
#   - CatBoost: only the shared 70% training sample is internally divided for
#     tuning; tune a 10-configuration grid, use early stopping, select by 
#     validation AUROC, then refit on the complete shared 70% training sample
#   - Both final models are evaluated on the same held-out 30% testing sample
#   - CatBoost native SHAP values and elastic-net centered additive log-odds
#     contributions summarized for the top linked exposures
#
# Notes on interpretation:
#   CatBoost SHAP values are native model SHAP values on the raw-formula
#   (log-odds) scale. For elastic net, beta_j * (x_ij - mean_training_j) is the
#   exact centered contribution of model-matrix feature j to the linear
#   predictor. It is a SHAP-style additive contribution on the same log-odds
#   scale. Correlated predictors can share or redistribute importance in both
#   models, so these plots describe prediction rather than causal effects.
# =============================================================================

rm(list = ls())

# -----------------------------------------------------------------------------
# Package check
# -----------------------------------------------------------------------------

required_packages <- c(
  "dplyr",
  "ggplot2",
  "Matrix",
  "glmnet",
  "catboost"
)

missing_packages <- required_packages[
  !vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)
]

if (length(missing_packages) > 0) {
  stop(
    "Install the following packages before running Code File 3: ",
    paste(missing_packages, collapse = ", "),
    "\nCatBoost R installation instructions: ",
    "https://catboost.ai/en/docs/installation/r-installation-binary-installation"
  )
}

suppressPackageStartupMessages({
  library(dplyr)
  library(ggplot2)
  library(Matrix)
  library(glmnet)
})

# =============================================================================
# USER SETTINGS: edit paths and analysis options here
# =============================================================================

# Current internal workshop directory.
# For GitHub Codespaces, change project_dir to the repository workspace path.
# Workshop directory — where docker-compose mounts the repository's
# ISSE26/ folder in the SPACESCANS RStudio container. Original authoring
# path: "/mnt/md0/Research Project/SPACESCANS/data/ISEE26Workshop"
project_dir <- "/home/rstudio/ISEE26Workshop"

attendee_dir <- file.path(project_dir, "forAttendee")
prelinked_dir <- file.path(project_dir, "prelinked_100k")
data_engineering_dir <- file.path(prelinked_dir, "1_DataEngineering")

# Code File 1 outputs.
input_rds <- file.path(
  data_engineering_dir,
  "ISEE26_workshop_merged_exposome.rds"
)
exposure_manifest_csv <- file.path(
  data_engineering_dir,
  "exposure_variable_manifest.csv"
)

# Feature labels, written by script 1 from the SPACESCANS feature dictionary
# that ships beside result.csv. Columns: varname, label, description — keyed
# by the merged variable names used here, so tables and figures read
# "Distance to primary road" rather than road_dist_pri. Absent (no dictionary
# in the run) means variable names are used as labels automatically.
feature_label_csv <- file.path(
  data_engineering_dir,
  "feature_labels.csv"
)

# All Code File 3 outputs are kept separate from ExWAS outputs.
output_dir <- file.path(prelinked_dir, "3_Prediction")
tables_dir <- file.path(output_dir, "tables")
figures_dir <- file.path(output_dir, "figures")
models_dir <- file.path(output_dir, "models")
predictions_dir <- file.path(output_dir, "predictions")
logs_dir <- file.path(output_dir, "logs")
rds_dir <- file.path(output_dir, "rds")

# Outcome, ID, and covariates.
id_var <- "PATID"
outcome_var <- "binary_outcome"
covariate_vars <- c("age", "sex", "race_eth")
categorical_covariates <- c("sex", "race_eth")

# Basic technical QC for linked exposures. No ExWAS association screening or
# pairwise-correlation pruning is used for prediction.
maximum_training_missing_fraction <- 0.80
minimum_training_unique_values <- 2L

# Reproducible stratified train/test split.
training_fraction <- 0.70
prediction_split_seed <- 20260806L

# Elastic-net tuning: same grid and five-fold AUROC tuning as AlphaEarth.
elastic_net_alpha_grid <- c(0, 0.25, 0.5, 0.75, 1)
elastic_net_n_folds <- 5L
elastic_net_fold_seed <- 20260603L

# Parallel CV is optional. FALSE is safer for a workshop Codespace. If TRUE,
# install doParallel and foreach and set a suitable worker count.
elastic_net_parallel <- FALSE
elastic_net_n_cores <- 5L

# CatBoost tuning: same internal validation fraction, early-stopping settings,
# and 10-configuration grid as the AlphaEarth code.
catboost_task_type <- "CPU"       # Change to "GPU" when available.
catboost_devices <- "0"
detected_cores <- parallel::detectCores(logical = TRUE)
if (is.na(detected_cores)) detected_cores <- 1L
catboost_thread_count <- max(1L, detected_cores - 1L)
catboost_random_seed <- 20260603L
catboost_validation_fraction <- 0.20
catboost_od_wait <- 300L
catboost_metric_period <- 250L
catboost_max_iterations <- 10000L

catboost_grid <- data.frame(
  config_id = seq_len(10L),
  depth = c(3, 4, 4, 5, 5, 5, 6, 6, 8, 8),
  learning_rate = c(
    0.01, 0.01, 0.02, 0.01, 0.02,
    0.03, 0.01, 0.02, 0.01, 0.02
  ),
  l2_leaf_reg = c(10, 10, 10, 15, 15, 15, 20, 20, 30, 30),
  random_strength = c(1, 1, 1, 1, 1, 1, 1, 1, 2, 2),
  bagging_temperature = c(0, 0, 0, 0.25, 0.25, 0.25, 0.5, 0.5, 1, 1),
  stringsAsFactors = FALSE
)

# SHAP/additive-contribution settings. A reproducible test-sample subset keeps
# the workshop runtime and plot size manageable. Increase shap_max_rows or set
# it to Inf to use the complete testing sample.
shap_max_rows <- 5000L
shap_seed <- 20260806L
top_n_importance_exposures <- 10L

# The requested figure ranks linked exposures only. Change to
# c("exposure", "covariate") to allow covariates into the top-10 figure.
importance_plot_roles <- "exposure"

# Figure dimensions.
performance_figure_width <- 11
performance_figure_height <- 6
importance_figure_width <- 14
importance_figure_height <- 8
figure_dpi <- 300

# =============================================================================
# Helper functions
# =============================================================================

timestamp_message <- function(...) {
  message(
    "[", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "] ",
    paste0(...)
  )
}

to_numeric_safely <- function(x) {
  if (is.numeric(x) || is.integer(x)) return(as.numeric(x))
  if (is.logical(x)) return(as.numeric(x))
  if (is.factor(x)) x <- as.character(x)
  suppressWarnings(as.numeric(x))
}

make_stratified_train_test_split <- function(
    y,
    train_fraction,
    seed
) {
  set.seed(seed)
  y <- as.integer(y)
  train <- logical(length(y))
  
  for (outcome_level in sort(unique(y))) {
    level_rows <- which(y == outcome_level)
    n_training <- floor(length(level_rows) * train_fraction)
    n_training <- max(1L, min(n_training, length(level_rows) - 1L))
    train[sample(level_rows, n_training)] <- TRUE
  }
  
  list(
    training_rows = which(train),
    testing_rows = which(!train)
  )
}

make_stratified_folds <- function(y, k, seed) {
  set.seed(seed)
  y <- as.integer(y)
  folds <- integer(length(y))
  
  for (outcome_level in sort(unique(y))) {
    level_rows <- sample(which(y == outcome_level))
    folds[level_rows] <- rep(seq_len(k), length.out = length(level_rows))
  }
  
  folds
}

make_stratified_validation_split <- function(y, validation_fraction, seed) {
  set.seed(seed)
  y <- as.integer(y)
  validation <- logical(length(y))
  
  for (outcome_level in sort(unique(y))) {
    level_rows <- which(y == outcome_level)
    n_validation <- max(1L, floor(length(level_rows) * validation_fraction))
    validation[sample(level_rows, n_validation)] <- TRUE
  }
  
  list(
    subtraining_rows = which(!validation),
    validation_rows = which(validation)
  )
}

prepare_predictor_frame <- function(
    dat,
    predictors,
    training_rows,
    categorical_variables
) {
  out <- dat[, predictors, drop = FALSE]
  categorical_variables <- intersect(categorical_variables, predictors)
  numeric_variables <- setdiff(predictors, categorical_variables)
  
  categorical_levels <- list()
  for (variable in categorical_variables) {
    x <- as.character(out[[variable]])
    x[is.na(x) | trimws(x) == ""] <- "__MISSING__"
    
    training_levels <- sort(unique(x[training_rows]))
    training_levels <- union(
      training_levels,
      c("__MISSING__", "__OTHER__")
    )
    
    x[!x %in% training_levels] <- "__OTHER__"
    out[[variable]] <- factor(x, levels = training_levels)
    categorical_levels[[variable]] <- training_levels
  }
  
  numeric_medians <- numeric(0)
  for (variable in numeric_variables) {
    x <- to_numeric_safely(out[[variable]])
    x[!is.finite(x)] <- NA_real_
    
    training_median <- median(x[training_rows], na.rm = TRUE)
    if (!is.finite(training_median)) {
      stop(
        "No finite training values are available for predictor: ",
        variable
      )
    }
    
    x[is.na(x)] <- training_median
    out[[variable]] <- x
    numeric_medians[variable] <- training_median
  }
  
  list(
    data = out,
    categorical_variables = categorical_variables,
    numeric_variables = numeric_variables,
    categorical_levels = categorical_levels,
    numeric_medians = numeric_medians
  )
}

clip_probability <- function(p, epsilon = 1e-6) {
  p <- as.numeric(p)
  p[p < epsilon] <- epsilon
  p[p > 1 - epsilon] <- 1 - epsilon
  p
}

calculate_auroc <- function(y, p) {
  y <- as.integer(y)
  p <- as.numeric(p)
  usable <- !is.na(y) & is.finite(p) & y %in% c(0L, 1L)
  y <- y[usable]
  p <- p[usable]
  
  n_cases <- sum(y == 1L)
  n_controls <- sum(y == 0L)
  if (n_cases == 0L || n_controls == 0L) return(NA_real_)
  
  probability_ranks <- rank(p, ties.method = "average")
  as.numeric(
    (
      sum(probability_ranks[y == 1L]) -
        n_cases * (n_cases + 1) / 2
    ) /
      (n_cases * n_controls)
  )
}

calculate_average_precision <- function(y, p) {
  y <- as.integer(y)
  p <- as.numeric(p)
  usable <- !is.na(y) & is.finite(p) & y %in% c(0L, 1L)
  y <- y[usable]
  p <- p[usable]
  
  n_cases <- sum(y == 1L)
  if (n_cases == 0L) return(NA_real_)
  
  order_by_risk <- order(p, decreasing = TRUE)
  y <- y[order_by_risk]
  true_positives <- cumsum(y == 1L)
  false_positives <- cumsum(y == 0L)
  precision <- true_positives / pmax(true_positives + false_positives, 1)
  
  mean(precision[y == 1L])
}

calculate_model_metrics <- function(y, p, model, analysis_set) {
  y <- as.integer(y)
  p <- clip_probability(p)
  
  calibration_model <- tryCatch(
    suppressWarnings(glm(
      y ~ qlogis(p),
      family = binomial(link = "logit")
    )),
    error = function(e) NULL
  )
  
  calibration_intercept <- NA_real_
  calibration_slope <- NA_real_
  if (!is.null(calibration_model) && length(coef(calibration_model)) >= 2L) {
    calibration_intercept <- unname(coef(calibration_model)[1])
    calibration_slope <- unname(coef(calibration_model)[2])
  }
  
  data.frame(
    model = model,
    analysis_set = analysis_set,
    n = length(y),
    cases = sum(y == 1L),
    controls = sum(y == 0L),
    prevalence = mean(y == 1L),
    auroc = calculate_auroc(y, p),
    auprc = calculate_average_precision(y, p),
    brier_score = mean((p - y)^2),
    log_loss = -mean(y * log(p) + (1 - y) * log(1 - p)),
    calibration_intercept = calibration_intercept,
    calibration_slope = calibration_slope,
    stringsAsFactors = FALSE
  )
}

make_roc_curve <- function(y, p, model) {
  y <- as.integer(y)
  order_by_risk <- order(p, decreasing = TRUE)
  y <- y[order_by_risk]
  
  true_positives <- cumsum(y == 1L)
  false_positives <- cumsum(y == 0L)
  n_cases <- sum(y == 1L)
  n_controls <- sum(y == 0L)
  
  data.frame(
    model = model,
    false_positive_rate = c(0, false_positives / n_controls, 1),
    true_positive_rate = c(0, true_positives / n_cases, 1),
    stringsAsFactors = FALSE
  )
}

make_precision_recall_curve <- function(y, p, model) {
  y <- as.integer(y)
  order_by_risk <- order(p, decreasing = TRUE)
  y <- y[order_by_risk]
  
  true_positives <- cumsum(y == 1L)
  false_positives <- cumsum(y == 0L)
  n_cases <- sum(y == 1L)
  
  data.frame(
    model = model,
    recall = c(0, true_positives / n_cases),
    precision = c(1, true_positives / pmax(true_positives + false_positives, 1)),
    stringsAsFactors = FALSE
  )
}

train_catboost_with_log <- function(
    training_pool,
    validation_pool,
    parameters,
    log_file
) {
  log_connection <- file(log_file, open = "wt")
  sink(log_connection, type = "output", split = TRUE)
  
  on.exit({
    while (sink.number(type = "output") > 0) {
      sink(type = "output")
    }
    close(log_connection)
  }, add = TRUE)
  
  catboost::catboost.train(
    learn_pool = training_pool,
    test_pool = validation_pool,
    params = parameters
  )
}

read_catboost_best_iteration <- function(log_file, requested_iterations) {
  log_lines <- tryCatch(
    readLines(log_file, warn = FALSE),
    error = function(e) character(0)
  )
  trimmed_lines <- trimws(log_lines)
  
  exact_hits <- grep(
    "^bestIteration\\s*=\\s*[0-9]+\\s*$",
    trimmed_lines,
    value = TRUE
  )
  
  if (length(exact_hits) > 0) {
    best_zero_based <- as.integer(sub(
      "^bestIteration\\s*=\\s*([0-9]+)\\s*$",
      "\\1",
      tail(exact_hits, 1L)
    ))
    
    return(list(
      iterations = min(requested_iterations, best_zero_based + 1L),
      source = "catboost_console_bestIteration_plus_1"
    ))
  }
  
  best_pattern_hits <- grep(
    "best:\\s*[-+0-9.eE]+\\s*\\([0-9]+\\)",
    log_lines,
    value = TRUE
  )
  
  if (length(best_pattern_hits) > 0) {
    last_hit <- tail(best_pattern_hits, 1L)
    match_object <- regexec(
      "best:\\s*[-+0-9.eE]+\\s*\\(([0-9]+)\\)",
      last_hit
    )
    matched_text <- regmatches(last_hit, match_object)[[1]]
    
    if (length(matched_text) >= 2L) {
      return(list(
        iterations = min(
          requested_iterations,
          as.integer(matched_text[2]) + 1L
        ),
        source = "catboost_console_best_pattern_plus_1"
      ))
    }
  }
  
  list(
    iterations = NA_integer_,
    source = "best_iteration_not_found_in_console_log"
  )
}

scale_feature_value <- function(x) {
  x <- to_numeric_safely(x)
  lower <- as.numeric(quantile(x, 0.05, na.rm = TRUE, names = FALSE))
  upper <- as.numeric(quantile(x, 0.95, na.rm = TRUE, names = FALSE))
  
  if (!is.finite(lower) || !is.finite(upper) || upper <= lower) {
    return(rep(0.5, length(x)))
  }
  
  scaled <- (x - lower) / (upper - lower)
  pmin(1, pmax(0, scaled))
}

# =============================================================================
# 1) Import data, manifest, and optional feature labels
# =============================================================================

if (!file.exists(input_rds)) {
  stop("Code File 1 merged RDS does not exist: ", input_rds)
}
if (!file.exists(exposure_manifest_csv)) {
  stop("Code File 1 exposure manifest does not exist: ", exposure_manifest_csv)
}

dir.create(tables_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(figures_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(models_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(predictions_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(logs_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(rds_dir, showWarnings = FALSE, recursive = TRUE)

timestamp_message("Reading merged workshop data: ", input_rds)
dat <- readRDS(input_rds)
exposure_manifest <- read.csv(
  exposure_manifest_csv,
  stringsAsFactors = FALSE,
  check.names = FALSE
)

if (!all(c("variable", "source") %in% names(exposure_manifest))) {
  stop("Exposure manifest must contain variable and source columns.")
}

required_columns <- c(id_var, outcome_var, covariate_vars)
missing_required_columns <- setdiff(required_columns, names(dat))
if (length(missing_required_columns) > 0) {
  stop(
    "Merged dataset is missing required columns: ",
    paste(missing_required_columns, collapse = ", ")
  )
}

dat[[id_var]] <- as.character(dat[[id_var]])
if (anyNA(dat[[id_var]]) || any(dat[[id_var]] == "")) {
  stop(id_var, " contains missing or blank values.")
}
if (anyDuplicated(dat[[id_var]])) {
  stop(id_var, " must be unique.")
}

dat[[outcome_var]] <- to_numeric_safely(dat[[outcome_var]])
dat <- dat[!is.na(dat[[outcome_var]]), , drop = FALSE]

if (!identical(sort(unique(dat[[outcome_var]])), c(0, 1))) {
  stop(outcome_var, " must contain exactly 0 and 1 after removing missing values.")
}

manifest_exposure_vars <- unique(exposure_manifest$variable)
exposure_vars_present <- intersect(manifest_exposure_vars, names(dat))
missing_manifest_exposures <- setdiff(manifest_exposure_vars, names(dat))

if (length(exposure_vars_present) == 0) {
  stop("No exposure-manifest variables were found in the merged dataset.")
}

if (length(missing_manifest_exposures) > 0) {
  warning(
    "Manifest variables absent from the merged dataset: ",
    paste(missing_manifest_exposures, collapse = ", ")
  )
}

# Label lookup defaults to the variable name. When the placeholder CSV becomes
# available, its nonblank labels replace the defaults.
feature_labels <- data.frame(
  varname = unique(c(covariate_vars, exposure_vars_present)),
  label = unique(c(covariate_vars, exposure_vars_present)),
  stringsAsFactors = FALSE
)

if (file.exists(feature_label_csv)) {
  supplied_labels <- read.csv(
    feature_label_csv,
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
  
  if (!all(c("varname", "label") %in% names(supplied_labels))) {
    stop("The feature label file must contain exactly the fields varname and label.")
  }
  
  supplied_labels <- supplied_labels |>
    select(varname, label) |>
    filter(!is.na(varname), varname != "") |>
    distinct(varname, .keep_all = TRUE)
  
  feature_labels <- feature_labels |>
    select(varname, default_label = label) |>
    left_join(supplied_labels, by = "varname") |>
    mutate(
      label = if_else(
        is.na(label) | trimws(label) == "",
        default_label,
        label
      )
    ) |>
    select(varname, label)
  
  timestamp_message("Using feature labels from: ", feature_label_csv)
} else {
  timestamp_message(
    "Feature label file not found; using variable names. Placeholder path: ",
    feature_label_csv
  )
}

# =============================================================================
# 2) Create the stratified 70% training / 30% testing split
# =============================================================================

# This one outer split is shared by both models, allowing a direct paired
# comparison of predictions and AUROCs in the same held-out participants.

y <- as.integer(dat[[outcome_var]])
split_rows <- make_stratified_train_test_split(
  y = y,
  train_fraction = training_fraction,
  seed = prediction_split_seed
)
training_rows <- split_rows$training_rows
testing_rows <- split_rows$testing_rows

dat$prediction_set <- ifelse(
  seq_len(nrow(dat)) %in% training_rows,
  "Training",
  "Testing"
)

split_summary <- bind_rows(
  data.frame(
    prediction_set = "Full sample",
    n = nrow(dat),
    cases = sum(y == 1L),
    controls = sum(y == 0L),
    prevalence = mean(y == 1L),
    stringsAsFactors = FALSE
  ),
  data.frame(
    prediction_set = "Training",
    n = length(training_rows),
    cases = sum(y[training_rows] == 1L),
    controls = sum(y[training_rows] == 0L),
    prevalence = mean(y[training_rows] == 1L),
    stringsAsFactors = FALSE
  ),
  data.frame(
    prediction_set = "Testing",
    n = length(testing_rows),
    cases = sum(y[testing_rows] == 1L),
    controls = sum(y[testing_rows] == 0L),
    prevalence = mean(y[testing_rows] == 1L),
    stringsAsFactors = FALSE
  )
)

split_assignment <- data.frame(
  PATID = dat[[id_var]],
  prediction_set = dat$prediction_set,
  stringsAsFactors = FALSE
)
names(split_assignment)[1] <- id_var

model_split_usage <- data.frame(
  model = c("Elastic net", "CatBoost"),
  outer_training_n = length(training_rows),
  outer_testing_n = length(testing_rows),
  outer_training_fraction = length(training_rows) / nrow(dat),
  outer_testing_fraction = length(testing_rows) / nrow(dat),
  split_rule = "Identical shared stratified 70% training / 30% testing split",
  stringsAsFactors = FALSE
)

timestamp_message(
  "Prediction split created: training n=", length(training_rows),
  "; testing n=", length(testing_rows)
)

# =============================================================================
# 3) Basic training-only exposure QC and predictor preprocessing
# =============================================================================

exposure_qc_rows <- lapply(exposure_vars_present, function(variable) {
  original_x <- dat[[variable]]
  numeric_x <- to_numeric_safely(original_x)
  numeric_x[!is.finite(numeric_x)] <- NA_real_
  
  original_nonmissing <- !is.na(original_x) &
    trimws(as.character(original_x)) != ""
  conversion_failure_n <- sum(original_nonmissing & is.na(numeric_x))
  
  training_x <- numeric_x[training_rows]
  training_nonmissing <- training_x[!is.na(training_x)]
  training_missing_fraction <- mean(is.na(training_x))
  training_unique_values <- length(unique(training_nonmissing))
  
  exclusion_reason <- dplyr::case_when(
    conversion_failure_n > 0 ~ "nonnumeric_exposure_values",
    length(training_nonmissing) == 0 ~ "all_training_values_missing",
    training_missing_fraction > maximum_training_missing_fraction ~
      "excessive_training_missingness",
    training_unique_values < minimum_training_unique_values ~
      "fewer_than_two_training_values",
    TRUE ~ NA_character_
  )
  
  data.frame(
    exposure = variable,
    n_total = length(numeric_x),
    training_n = length(training_x),
    training_n_nonmissing = length(training_nonmissing),
    training_missing_fraction = training_missing_fraction,
    training_unique_values = training_unique_values,
    conversion_failure_n = conversion_failure_n,
    training_min = if (length(training_nonmissing) > 0) {
      min(training_nonmissing)
    } else {
      NA_real_
    },
    training_mean = if (length(training_nonmissing) > 0) {
      mean(training_nonmissing)
    } else {
      NA_real_
    },
    training_sd = if (length(training_nonmissing) > 1) {
      sd(training_nonmissing)
    } else {
      NA_real_
    },
    training_max = if (length(training_nonmissing) > 0) {
      max(training_nonmissing)
    } else {
      NA_real_
    },
    exclusion_reason = exclusion_reason,
    included_in_prediction = is.na(exclusion_reason),
    stringsAsFactors = FALSE
  )
})

exposure_qc <- bind_rows(exposure_qc_rows) |>
  left_join(
    exposure_manifest |>
      select(variable, source) |>
      distinct(variable, .keep_all = TRUE),
    by = c("exposure" = "variable")
  ) |>
  arrange(source, exposure)

eligible_exposure_vars <- exposure_qc |>
  filter(included_in_prediction) |>
  pull(exposure)

if (length(eligible_exposure_vars) == 0) {
  stop("No linked exposures passed basic prediction QC.")
}

# Convert eligible linked exposures to numeric before common preprocessing.
for (variable in eligible_exposure_vars) {
  dat[[variable]] <- to_numeric_safely(dat[[variable]])
  dat[[variable]][!is.finite(dat[[variable]])] <- NA_real_
}

# Numeric covariates must also be convertible. Categorical covariates are
# handled as factors with levels learned from training data.
numeric_covariates <- setdiff(covariate_vars, categorical_covariates)
for (variable in numeric_covariates) {
  original_x <- dat[[variable]]
  numeric_x <- to_numeric_safely(original_x)
  conversion_failures <- sum(!is.na(original_x) & is.na(numeric_x))
  if (conversion_failures > 0) {
    stop("Nonnumeric values found in numeric covariate: ", variable)
  }
  dat[[variable]] <- numeric_x
}

predictor_vars <- unique(c(covariate_vars, eligible_exposure_vars))

preprocessing <- prepare_predictor_frame(
  dat = dat,
  predictors = predictor_vars,
  training_rows = training_rows,
  categorical_variables = categorical_covariates
)
predictor_frame <- preprocessing$data

source_to_category <- c(
  "zbp_primary_cbp_fallback" = "Social capital",
  "noise_270m" = "Noise",
  "tiger_road_proximity" = "Road proximity",
  "block_group_ndi" = "Neighborhood deprivation",
  "block_group_walkability" = "Walkability",
  "nhd_blue_space_proximity" = "Blue space",
  "visible_nighttime_light" = "Light at night",
  "temis_uv" = "Ultraviolet",
  "tract_fara_food_access" = "Food access"
)

predictor_manifest <- bind_rows(
  data.frame(
    variable = covariate_vars,
    source = "demographic_covariate",
    role = "covariate",
    stringsAsFactors = FALSE
  ),
  exposure_manifest |>
    filter(variable %in% eligible_exposure_vars) |>
    select(variable, source) |>
    distinct(variable, .keep_all = TRUE) |>
    mutate(role = "exposure")
) |>
  mutate(
    category = unname(source_to_category[source]),
    category = if_else(is.na(category), source, category),
    predictor_type = if_else(
      variable %in% preprocessing$categorical_variables,
      "categorical",
      "numeric"
    )
  ) |>
  left_join(feature_labels, by = c("variable" = "varname")) |>
  arrange(role, category, variable)

timestamp_message(
  "Predictors prepared: covariates=", length(covariate_vars),
  "; linked exposures=", length(eligible_exposure_vars),
  "; total=", length(predictor_vars)
)

# =============================================================================
# 4) Elastic-net logistic regression: five-fold AUROC tuning
# =============================================================================

timestamp_message("Creating elastic-net sparse model matrix...")
elastic_formula <- reformulate(
  termlabels = predictor_vars,
  intercept = FALSE
)

x_all <- Matrix::sparse.model.matrix(
  elastic_formula,
  data = as.data.frame(predictor_frame)
)

matrix_assign <- attr(x_all, "assign")
formula_terms <- gsub(
  "`",
  "",
  attr(terms(elastic_formula), "term.labels"),
  fixed = TRUE
)

if (is.null(matrix_assign) || length(matrix_assign) != ncol(x_all)) {
  stop("Could not map elastic-net model-matrix columns to original predictors.")
}

matrix_feature_map <- data.frame(
  matrix_feature = colnames(x_all),
  original_variable = formula_terms[matrix_assign],
  stringsAsFactors = FALSE
)

x_training <- x_all[training_rows, , drop = FALSE]
x_testing <- x_all[testing_rows, , drop = FALSE]
y_training <- y[training_rows]
y_testing <- y[testing_rows]

# Remove model-matrix columns with zero training variation. Original linked
# exposures were already screened, but unused categorical levels can create
# constant dummy columns.
training_column_mean <- Matrix::colMeans(x_training)
training_column_second_moment <- Matrix::colMeans(x_training * x_training)
training_column_variance <- pmax(
  0,
  training_column_second_moment - training_column_mean^2
)
nonconstant_matrix_columns <- is.finite(training_column_variance) &
  training_column_variance > 1e-12

excluded_matrix_columns <- matrix_feature_map[!nonconstant_matrix_columns, ]
matrix_feature_map <- matrix_feature_map[nonconstant_matrix_columns, ]
x_all <- x_all[, nonconstant_matrix_columns, drop = FALSE]
x_training <- x_training[, nonconstant_matrix_columns, drop = FALSE]
x_testing <- x_testing[, nonconstant_matrix_columns, drop = FALSE]

training_column_mean <- Matrix::colMeans(x_training)

if (ncol(x_training) == 0) {
  stop("No nonconstant elastic-net model-matrix columns remain.")
}

elastic_net_fold_id <- make_stratified_folds(
  y = y_training,
  k = elastic_net_n_folds,
  seed = elastic_net_fold_seed
)

elastic_net_cluster <- NULL
if (isTRUE(elastic_net_parallel)) {
  if (!requireNamespace("doParallel", quietly = TRUE) ||
      !requireNamespace("foreach", quietly = TRUE)) {
    stop(
      "Install doParallel and foreach, or set elastic_net_parallel <- FALSE."
    )
  }
  
  elastic_net_cluster <- parallel::makeCluster(elastic_net_n_cores)
  doParallel::registerDoParallel(elastic_net_cluster)
  on.exit({
    try(parallel::stopCluster(elastic_net_cluster), silent = TRUE)
    try(foreach::registerDoSEQ(), silent = TRUE)
  }, add = TRUE)
}

elastic_net_tuning_rows <- list()
best_elastic_net_fit <- NULL
best_elastic_net_row <- NULL

for (alpha_value in elastic_net_alpha_grid) {
  timestamp_message("Tuning elastic net: alpha=", alpha_value)
  fit_start <- Sys.time()
  
  current_cv_fit <- glmnet::cv.glmnet(
    x = x_training,
    y = y_training,
    family = "binomial",
    alpha = alpha_value,
    foldid = elastic_net_fold_id,
    type.measure = "auc",
    standardize = TRUE,
    keep = FALSE,
    parallel = elastic_net_parallel
  )
  
  lambda_min_index <- which.min(
    abs(current_cv_fit$lambda - current_cv_fit$lambda.min)
  )
  lambda_1se_index <- which.min(
    abs(current_cv_fit$lambda - current_cv_fit$lambda.1se)
  )
  
  current_tuning_row <- data.frame(
    alpha = alpha_value,
    lambda_min = current_cv_fit$lambda.min,
    lambda_1se = current_cv_fit$lambda.1se,
    cv_auroc_lambda_min = current_cv_fit$cvm[lambda_min_index],
    cv_auroc_lambda_1se = current_cv_fit$cvm[lambda_1se_index],
    cv_auroc_sd_lambda_min = current_cv_fit$cvsd[lambda_min_index],
    cv_auroc_sd_lambda_1se = current_cv_fit$cvsd[lambda_1se_index],
    elapsed_minutes = as.numeric(difftime(
      Sys.time(),
      fit_start,
      units = "mins"
    )),
    stringsAsFactors = FALSE
  )
  
  elastic_net_tuning_rows[[as.character(alpha_value)]] <- current_tuning_row
  
  if (is.null(best_elastic_net_row) ||
      current_tuning_row$cv_auroc_lambda_min >
      best_elastic_net_row$cv_auroc_lambda_min) {
    best_elastic_net_row <- current_tuning_row
    best_elastic_net_fit <- current_cv_fit
  }
}

elastic_net_tuning <- bind_rows(elastic_net_tuning_rows) |>
  mutate(
    selected = alpha == best_elastic_net_row$alpha &
      lambda_min == best_elastic_net_row$lambda_min
  )

elastic_net_training_probability <- as.numeric(predict(
  best_elastic_net_fit,
  newx = x_training,
  s = "lambda.min",
  type = "response"
))
elastic_net_testing_probability <- as.numeric(predict(
  best_elastic_net_fit,
  newx = x_testing,
  s = "lambda.min",
  type = "response"
))

elastic_net_metrics <- bind_rows(
  calculate_model_metrics(
    y_training,
    elastic_net_training_probability,
    "Elastic net",
    "Training"
  ),
  calculate_model_metrics(
    y_testing,
    elastic_net_testing_probability,
    "Elastic net",
    "Testing"
  )
)

elastic_net_predictions <- bind_rows(
  data.frame(
    PATID = dat[[id_var]][training_rows],
    prediction_set = "Training",
    outcome = y_training,
    predicted_probability = elastic_net_training_probability,
    model = "Elastic net",
    stringsAsFactors = FALSE
  ),
  data.frame(
    PATID = dat[[id_var]][testing_rows],
    prediction_set = "Testing",
    outcome = y_testing,
    predicted_probability = elastic_net_testing_probability,
    model = "Elastic net",
    stringsAsFactors = FALSE
  )
)
names(elastic_net_predictions)[1] <- id_var

elastic_net_coefficient_matrix <- as.matrix(coef(
  best_elastic_net_fit,
  s = "lambda.min"
))
elastic_net_coefficients <- data.frame(
  matrix_feature = rownames(elastic_net_coefficient_matrix),
  coefficient = as.numeric(elastic_net_coefficient_matrix[, 1]),
  stringsAsFactors = FALSE
) |>
  filter(matrix_feature != "(Intercept)") |>
  left_join(matrix_feature_map, by = "matrix_feature") |>
  left_join(
    predictor_manifest |>
      select(
        original_variable = variable,
        source,
        category,
        role,
        label
      ),
    by = "original_variable"
  ) |>
  arrange(desc(abs(coefficient)))

saveRDS(
  list(
    cv_fit = best_elastic_net_fit,
    selected_tuning = best_elastic_net_row,
    tuning = elastic_net_tuning,
    formula = elastic_formula,
    matrix_feature_map = matrix_feature_map,
    training_column_mean = training_column_mean,
    preprocessing = preprocessing
  ),
  file.path(models_dir, "elastic_net_model.rds"),
  compress = FALSE
)

timestamp_message(
  "Elastic net selected: alpha=", best_elastic_net_row$alpha,
  "; lambda.min=", signif(best_elastic_net_row$lambda_min, 5),
  "; CV AUROC=", round(best_elastic_net_row$cv_auroc_lambda_min, 4)
)

# =============================================================================
# 5) CatBoost: shared 70/30 outer split plus training-only internal tuning
# =============================================================================

catboost_task_type <- toupper(catboost_task_type)
if (!catboost_task_type %in% c("CPU", "GPU")) {
  stop("catboost_task_type must be CPU or GPU.")
}

catboost_internal_split <- make_stratified_validation_split(
  y = y_training,
  validation_fraction = catboost_validation_fraction,
  seed = catboost_random_seed
)

catboost_subtraining_rows <- training_rows[
  catboost_internal_split$subtraining_rows
]
catboost_validation_rows <- training_rows[
  catboost_internal_split$validation_rows
]

# Confirm that CatBoost's tuning rows come exclusively from the shared 70%
# training sample and that the shared 30% testing sample remains untouched.
if (!all(catboost_subtraining_rows %in% training_rows) ||
    !all(catboost_validation_rows %in% training_rows) ||
    any(catboost_subtraining_rows %in% testing_rows) ||
    any(catboost_validation_rows %in% testing_rows)) {
  stop("CatBoost internal tuning rows are inconsistent with the shared 70/30 split.")
}

# The predictor frame uses training-only levels and medians. Factor columns are
# recognized automatically as categorical predictors by CatBoost R.
catboost_frame <- predictor_frame

load_catboost_pool <- function(rows, labels) {
  catboost::catboost.load_pool(
    data = as.data.frame(catboost_frame[rows, , drop = FALSE]),
    label = labels[rows]
  )
}

catboost_subtraining_pool <- load_catboost_pool(catboost_subtraining_rows, y)
catboost_validation_pool <- load_catboost_pool(catboost_validation_rows, y)
catboost_training_pool <- load_catboost_pool(training_rows, y)
catboost_testing_pool <- load_catboost_pool(testing_rows, y)

catboost_tuning_rows <- list()
best_catboost_auc <- -Inf
best_catboost_config <- NULL
best_catboost_iterations <- NA_integer_

for (config_row in seq_len(nrow(catboost_grid))) {
  current_config <- catboost_grid[config_row, , drop = FALSE]
  current_log_file <- file.path(
    logs_dir,
    sprintf("catboost_tuning_config_%02d.log", current_config$config_id)
  )
  
  timestamp_message(
    "Tuning CatBoost configuration ", config_row, "/", nrow(catboost_grid),
    ": depth=", current_config$depth,
    "; learning_rate=", current_config$learning_rate,
    "; l2_leaf_reg=", current_config$l2_leaf_reg
  )
  
  current_parameters <- list(
    loss_function = "Logloss",
    eval_metric = "AUC",
    iterations = catboost_max_iterations,
    depth = current_config$depth,
    learning_rate = current_config$learning_rate,
    l2_leaf_reg = current_config$l2_leaf_reg,
    random_strength = current_config$random_strength,
    bagging_temperature = current_config$bagging_temperature,
    od_type = "Iter",
    od_wait = catboost_od_wait,
    random_seed = catboost_random_seed,
    thread_count = catboost_thread_count,
    use_best_model = TRUE,
    allow_writing_files = FALSE,
    logging_level = "Verbose",
    metric_period = catboost_metric_period,
    task_type = catboost_task_type
  )
  if (catboost_task_type == "GPU") {
    current_parameters$devices <- catboost_devices
  }
  
  fit_start <- Sys.time()
  current_model <- train_catboost_with_log(
    training_pool = catboost_subtraining_pool,
    validation_pool = catboost_validation_pool,
    parameters = current_parameters,
    log_file = current_log_file
  )
  
  validation_probability <- as.numeric(catboost::catboost.predict(
    current_model,
    catboost_validation_pool,
    prediction_type = "Probability"
  ))
  validation_auroc <- calculate_auroc(
    y[catboost_validation_rows],
    validation_probability
  )
  validation_auprc <- calculate_average_precision(
    y[catboost_validation_rows],
    validation_probability
  )
  
  iteration_information <- read_catboost_best_iteration(
    current_log_file,
    catboost_max_iterations
  )
  
  if (is.na(iteration_information$iterations)) {
    stop(
      "CatBoost completed but its early-stopped best iteration could not be ",
      "read from: ", current_log_file,
      "\nReview the CatBoost installation/logging behavior before final refitting."
    )
  }
  
  catboost_tuning_rows[[config_row]] <- data.frame(
    current_config,
    requested_iterations = catboost_max_iterations,
    selected_iterations = iteration_information$iterations,
    selected_iterations_source = iteration_information$source,
    validation_auroc = validation_auroc,
    validation_auprc = validation_auprc,
    elapsed_minutes = as.numeric(difftime(
      Sys.time(),
      fit_start,
      units = "mins"
    )),
    stringsAsFactors = FALSE
  )
  
  if (is.finite(validation_auroc) && validation_auroc > best_catboost_auc) {
    best_catboost_auc <- validation_auroc
    best_catboost_config <- current_config
    best_catboost_iterations <- iteration_information$iterations
  }
  
  rm(current_model, validation_probability)
  gc(verbose = FALSE)
}

if (is.null(best_catboost_config) || is.na(best_catboost_iterations)) {
  stop("CatBoost tuning did not produce a selectable configuration.")
}

catboost_tuning <- bind_rows(catboost_tuning_rows) |>
  mutate(selected = config_id == best_catboost_config$config_id)

final_catboost_parameters <- list(
  loss_function = "Logloss",
  eval_metric = "AUC",
  iterations = best_catboost_iterations,
  depth = best_catboost_config$depth,
  learning_rate = best_catboost_config$learning_rate,
  l2_leaf_reg = best_catboost_config$l2_leaf_reg,
  random_strength = best_catboost_config$random_strength,
  bagging_temperature = best_catboost_config$bagging_temperature,
  random_seed = catboost_random_seed,
  thread_count = catboost_thread_count,
  allow_writing_files = FALSE,
  logging_level = "Verbose",
  metric_period = catboost_metric_period,
  task_type = catboost_task_type
)
if (catboost_task_type == "GPU") {
  final_catboost_parameters$devices <- catboost_devices
}

timestamp_message(
  "Refitting selected CatBoost configuration on the complete training sample..."
)
final_catboost_model <- catboost::catboost.train(
  learn_pool = catboost_training_pool,
  params = final_catboost_parameters
)

catboost_training_probability <- as.numeric(catboost::catboost.predict(
  final_catboost_model,
  catboost_training_pool,
  prediction_type = "Probability"
))
catboost_testing_probability <- as.numeric(catboost::catboost.predict(
  final_catboost_model,
  catboost_testing_pool,
  prediction_type = "Probability"
))

catboost_metrics <- bind_rows(
  calculate_model_metrics(
    y_training,
    catboost_training_probability,
    "CatBoost",
    "Training"
  ),
  calculate_model_metrics(
    y_testing,
    catboost_testing_probability,
    "CatBoost",
    "Testing"
  )
)

catboost_predictions <- bind_rows(
  data.frame(
    PATID = dat[[id_var]][training_rows],
    prediction_set = "Training",
    outcome = y_training,
    predicted_probability = catboost_training_probability,
    model = "CatBoost",
    stringsAsFactors = FALSE
  ),
  data.frame(
    PATID = dat[[id_var]][testing_rows],
    prediction_set = "Testing",
    outcome = y_testing,
    predicted_probability = catboost_testing_probability,
    model = "CatBoost",
    stringsAsFactors = FALSE
  )
)
names(catboost_predictions)[1] <- id_var

catboost_model_file <- file.path(models_dir, "catboost_model.cbm")
catboost::catboost.save_model(final_catboost_model, catboost_model_file)
saveRDS(
  list(
    selected_config = best_catboost_config,
    selected_iterations = best_catboost_iterations,
    validation_auroc = best_catboost_auc,
    tuning = catboost_tuning,
    preprocessing = preprocessing,
    predictor_order = predictor_vars,
    catboost_model_file = catboost_model_file
  ),
  file.path(models_dir, "catboost_model_metadata.rds"),
  compress = FALSE
)

timestamp_message(
  "CatBoost selected: configuration=", best_catboost_config$config_id,
  "; iterations=", best_catboost_iterations,
  "; validation AUROC=", round(best_catboost_auc, 4)
)

# =============================================================================
# 6) Held-out performance tables and figures
# =============================================================================

model_metrics <- bind_rows(elastic_net_metrics, catboost_metrics) |>
  arrange(analysis_set, model)

all_predictions <- bind_rows(
  elastic_net_predictions,
  catboost_predictions
)

testing_predictions <- all_predictions |>
  filter(prediction_set == "Testing")

roc_curve_data <- bind_rows(
  make_roc_curve(
    y_testing,
    elastic_net_testing_probability,
    "Elastic net"
  ),
  make_roc_curve(
    y_testing,
    catboost_testing_probability,
    "CatBoost"
  )
)

precision_recall_data <- bind_rows(
  make_precision_recall_curve(
    y_testing,
    elastic_net_testing_probability,
    "Elastic net"
  ),
  make_precision_recall_curve(
    y_testing,
    catboost_testing_probability,
    "CatBoost"
  )
)

test_metric_labels <- model_metrics |>
  filter(analysis_set == "Testing") |>
  mutate(
    roc_label = paste0(model, " (AUROC=", sprintf("%.3f", auroc), ")"),
    pr_label = paste0(model, " (AUPRC=", sprintf("%.3f", auprc), ")")
  )

roc_curve_data <- roc_curve_data |>
  left_join(
    test_metric_labels |>
      select(model, plot_model = roc_label),
    by = "model"
  ) |>
  mutate(curve = "ROC curve", x = false_positive_rate, y = true_positive_rate)

precision_recall_data <- precision_recall_data |>
  left_join(
    test_metric_labels |>
      select(model, plot_model = pr_label),
    by = "model"
  ) |>
  mutate(curve = "Precision–recall curve", x = recall, y = precision)

performance_curve_data <- bind_rows(
  roc_curve_data |>
    select(model, plot_model, curve, x, y),
  precision_recall_data |>
    select(model, plot_model, curve, x, y)
)

performance_curve_plot <- ggplot(
  performance_curve_data,
  aes(x = x, y = y, color = plot_model)
) +
  geom_line(linewidth = 1) +
  facet_wrap(~curve, nrow = 1) +
  coord_equal() +
  scale_x_continuous(limits = c(0, 1)) +
  scale_y_continuous(limits = c(0, 1)) +
  labs(
    title = "Held-out testing-sample discrimination",
    x = "False-positive rate / Recall",
    y = "True-positive rate / Precision",
    color = NULL
  ) +
  theme_bw(base_size = 12) +
  theme(legend.position = "bottom")

# Dedicated ROC/AUROC comparison matching the requested presentation: the
# x-axis shows specificity from 1 to 0, the y-axis shows sensitivity, and both
# curves use predictions from the identical held-out 30% testing sample.
roc_auc_comparison_plot <- ggplot(
  roc_curve_data,
  aes(
    x = 1 - false_positive_rate,
    y = true_positive_rate,
    color = plot_model,
    linetype = plot_model
  )
) +
  annotate(
    "segment",
    x = 1,
    y = 0,
    xend = 0,
    yend = 1,
    color = "grey70",
    linewidth = 0.6
  ) +
  geom_line(linewidth = 1) +
  scale_x_reverse(
    limits = c(1, 0),
    breaks = seq(1, 0, by = -0.2)
  ) +
  scale_y_continuous(
    limits = c(0, 1),
    breaks = seq(0, 1, by = 0.2)
  ) +
  coord_equal() +
  labs(
    title = "ROC comparison of elastic net and CatBoost",
    subtitle = "Both models evaluated in the identical held-out 30% testing sample",
    x = "Specificity",
    y = "Sensitivity",
    color = NULL,
    linetype = NULL
  ) +
  theme_classic(base_size = 12) +
  theme(
    legend.position = "bottom",
    legend.box = "vertical"
  )

calibration_by_decile <- testing_predictions |>
  group_by(model) |>
  mutate(calibration_group = ntile(predicted_probability, 10)) |>
  group_by(model, calibration_group) |>
  summarise(
    n = n(),
    cases = sum(outcome == 1),
    mean_predicted_probability = mean(predicted_probability),
    observed_proportion = mean(outcome),
    .groups = "drop"
  )

calibration_plot <- ggplot(
  calibration_by_decile,
  aes(
    x = mean_predicted_probability,
    y = observed_proportion,
    color = model
  )
) +
  geom_abline(intercept = 0, slope = 1, linetype = "dashed") +
  geom_line(linewidth = 0.8) +
  geom_point(size = 2) +
  coord_equal() +
  scale_x_continuous(limits = c(0, 1)) +
  scale_y_continuous(limits = c(0, 1)) +
  labs(
    title = "Held-out testing-sample calibration",
    subtitle = "Observed versus mean predicted risk within prediction deciles",
    x = "Mean predicted probability",
    y = "Observed outcome proportion",
    color = NULL
  ) +
  theme_bw(base_size = 12) +
  theme(legend.position = "bottom")

# =============================================================================
# 7) CatBoost SHAP and elastic-net additive contributions
# =============================================================================

set.seed(shap_seed)
if (is.infinite(shap_max_rows) || length(testing_rows) <= shap_max_rows) {
  shap_rows <- testing_rows
} else {
  shap_rows <- sort(sample(testing_rows, shap_max_rows, replace = FALSE))
}

timestamp_message(
  "Calculating interpretation values for ", length(shap_rows),
  " held-out testing observations..."
)

# CatBoost native SHAP values. For binary Logloss models, these are additive on
# the raw-formula/log-odds scale. The final column is the expected value.
catboost_shap_pool <- load_catboost_pool(shap_rows, y)
catboost_shap_with_baseline <- catboost::catboost.get_feature_importance(
  final_catboost_model,
  pool = catboost_shap_pool,
  type = "ShapValues",
  thread_count = catboost_thread_count
)
catboost_shap_with_baseline <- as.matrix(catboost_shap_with_baseline)

if (ncol(catboost_shap_with_baseline) != length(predictor_vars) + 1L) {
  stop(
    "Unexpected CatBoost SHAP dimensions: expected ",
    length(predictor_vars) + 1L,
    " columns; received ", ncol(catboost_shap_with_baseline), "."
  )
}

catboost_shap <- catboost_shap_with_baseline[
  ,
  seq_along(predictor_vars),
  drop = FALSE
]
colnames(catboost_shap) <- predictor_vars
catboost_expected_value <- catboost_shap_with_baseline[
  ,
  ncol(catboost_shap_with_baseline)
]

# Elastic-net centered additive contributions. Contributions from multiple
# dummy columns belonging to the same original variable are summed.
elastic_net_beta <- elastic_net_coefficient_matrix[
  colnames(x_all),
  1
]
elastic_net_shap_matrix <- as.matrix(x_all[shap_rows, , drop = FALSE])
elastic_net_shap_matrix <- sweep(
  elastic_net_shap_matrix,
  MARGIN = 2,
  STATS = training_column_mean,
  FUN = "-"
)
elastic_net_shap_matrix <- sweep(
  elastic_net_shap_matrix,
  MARGIN = 2,
  STATS = elastic_net_beta,
  FUN = "*"
)

elastic_net_variable_contributions <- matrix(
  0,
  nrow = length(shap_rows),
  ncol = length(predictor_vars),
  dimnames = list(NULL, predictor_vars)
)

for (variable in predictor_vars) {
  variable_columns <- which(
    matrix_feature_map$original_variable == variable
  )
  
  if (length(variable_columns) == 1L) {
    elastic_net_variable_contributions[, variable] <-
      elastic_net_shap_matrix[, variable_columns]
  } else if (length(variable_columns) > 1L) {
    elastic_net_variable_contributions[, variable] <- rowSums(
      elastic_net_shap_matrix[, variable_columns, drop = FALSE]
    )
  }
}

feature_importance <- bind_rows(
  data.frame(
    model = "Elastic net",
    variable = predictor_vars,
    mean_absolute_contribution = colMeans(
      abs(elastic_net_variable_contributions)
    ),
    interpretation_method =
      "Centered beta times model-matrix value, aggregated to original variable",
    interpretation_scale = "log_odds",
    n_interpretation_rows = length(shap_rows),
    stringsAsFactors = FALSE
  ),
  data.frame(
    model = "CatBoost",
    variable = predictor_vars,
    mean_absolute_contribution = colMeans(abs(catboost_shap)),
    interpretation_method = "CatBoost native SHAP values",
    interpretation_scale = "raw_formula_log_odds",
    n_interpretation_rows = length(shap_rows),
    stringsAsFactors = FALSE
  )
) |>
  left_join(
    predictor_manifest |>
      select(variable, source, category, role, label),
    by = "variable"
  ) |>
  group_by(model) |>
  arrange(desc(mean_absolute_contribution), .by_group = TRUE) |>
  mutate(overall_importance_rank = row_number()) |>
  ungroup()

top_importance_exposures <- feature_importance |>
  filter(role %in% importance_plot_roles) |>
  group_by(model) |>
  slice_max(
    order_by = mean_absolute_contribution,
    n = top_n_importance_exposures,
    with_ties = FALSE
  ) |>
  arrange(model, mean_absolute_contribution) |>
  ungroup()

shap_plot_rows <- list()
shap_plot_i <- 1L

for (model_name in c("Elastic net", "CatBoost")) {
  selected_features <- top_importance_exposures |>
    filter(model == model_name) |>
    arrange(mean_absolute_contribution)
  
  for (feature_row in seq_len(nrow(selected_features))) {
    variable <- selected_features$variable[feature_row]
    display_label <- selected_features$label[feature_row]
    mean_absolute_value <-
      selected_features$mean_absolute_contribution[feature_row]
    
    contribution <- if (model_name == "Elastic net") {
      elastic_net_variable_contributions[, variable]
    } else {
      catboost_shap[, variable]
    }
    
    feature_value <- predictor_frame[[variable]][shap_rows]
    
    shap_plot_rows[[shap_plot_i]] <- data.frame(
      model = model_name,
      variable = variable,
      display_label = display_label,
      feature_axis_label = paste0(
        display_label,
        "  |mean|=",
        sprintf("%.3f", mean_absolute_value)
      ),
      contribution = contribution,
      feature_value_scaled = scale_feature_value(feature_value),
      mean_absolute_contribution = mean_absolute_value,
      stringsAsFactors = FALSE
    )
    shap_plot_i <- shap_plot_i + 1L
  }
}

shap_plot_data <- bind_rows(shap_plot_rows) |>
  mutate(
    model_feature_key = paste(model, feature_axis_label, sep = "___")
  )

feature_axis_levels <- top_importance_exposures |>
  mutate(
    feature_axis_label = paste0(
      label,
      "  |mean|=",
      sprintf("%.3f", mean_absolute_contribution)
    ),
    model_feature_key = paste(model, feature_axis_label, sep = "___")
  ) |>
  arrange(model, mean_absolute_contribution) |>
  pull(model_feature_key) |>
  unique()

shap_plot_data$model_feature_key <- factor(
  shap_plot_data$model_feature_key,
  levels = feature_axis_levels
)

importance_beeswarm_plot <- ggplot(
  shap_plot_data,
  aes(
    x = contribution,
    y = model_feature_key,
    color = feature_value_scaled
  )
) +
  geom_vline(xintercept = 0, color = "grey55", linewidth = 0.5) +
  geom_point(
    position = position_jitter(width = 0, height = 0.16, seed = shap_seed),
    alpha = 0.45,
    size = 0.75
  ) +
  facet_wrap(~model, nrow = 1, scales = "free_y") +
  scale_y_discrete(
    labels = function(x) sub("^.*___", "", x)
  ) +
  scale_color_gradient(
    low = "#440154",
    high = "#FDE725",
    limits = c(0, 1)
  ) +
  labs(
    title = paste0(
      "Top ", top_n_importance_exposures,
      " linked exposures by mean absolute contribution"
    ),
    subtitle = paste0(
      "Held-out test subset (n=", length(shap_rows),
      "); CatBoost native SHAP and elastic-net centered additive contributions"
    ),
    x = "Contribution to predicted log odds",
    y = NULL,
    color = "Feature value\nLow to high"
  ) +
  theme_bw(base_size = 11) +
  theme(
    legend.position = "right",
    panel.grid.minor = element_blank(),
    strip.text = element_text(face = "bold"),
    axis.text.y = element_text(size = 9)
  )

importance_bar_plot <- ggplot(
  top_importance_exposures |>
    mutate(model_variable = paste(model, label, sep = "___")),
  aes(
    x = mean_absolute_contribution,
    y = reorder(model_variable, mean_absolute_contribution),
    fill = category
  )
) +
  geom_col() +
  facet_wrap(~model, nrow = 1, scales = "free_y") +
  scale_y_discrete(labels = function(x) sub("^.*___", "", x)) +
  labs(
    title = "Mean absolute contribution of the top linked exposures",
    x = "Mean absolute contribution to predicted log odds",
    y = NULL,
    fill = "Exposure category"
  ) +
  theme_bw(base_size = 11) +
  theme(legend.position = "bottom")

# =============================================================================
# 8) Save all outputs
# =============================================================================

# This template can be copied to the feature_label_csv path and edited later.
write.csv(
  feature_labels,
  file.path(output_dir, "feature_labels_template.csv"),
  row.names = FALSE
)

write.csv(
  split_summary,
  file.path(tables_dir, "01_prediction_train_test_split_summary.csv"),
  row.names = FALSE
)
write.csv(
  split_assignment,
  file.path(tables_dir, "02_prediction_train_test_split_assignment.csv"),
  row.names = FALSE
)
write.csv(
  model_split_usage,
  file.path(tables_dir, "02a_shared_70_30_split_model_usage.csv"),
  row.names = FALSE
)
write.csv(
  exposure_qc,
  file.path(tables_dir, "03_prediction_exposure_qc.csv"),
  row.names = FALSE
)
write.csv(
  predictor_manifest,
  file.path(tables_dir, "04_prediction_predictor_manifest.csv"),
  row.names = FALSE
)
write.csv(
  excluded_matrix_columns,
  file.path(tables_dir, "05_elastic_net_excluded_constant_matrix_columns.csv"),
  row.names = FALSE
)
write.csv(
  elastic_net_tuning,
  file.path(tables_dir, "06_elastic_net_tuning_results.csv"),
  row.names = FALSE
)
write.csv(
  catboost_tuning,
  file.path(tables_dir, "07_catboost_tuning_results.csv"),
  row.names = FALSE
)
write.csv(
  model_metrics,
  file.path(tables_dir, "08_prediction_model_performance.csv"),
  row.names = FALSE
)
write.csv(
  elastic_net_coefficients,
  file.path(tables_dir, "09_elastic_net_coefficients.csv"),
  row.names = FALSE
)
write.csv(
  feature_importance,
  file.path(tables_dir, "10_feature_importance_all_predictors.csv"),
  row.names = FALSE
)
write.csv(
  top_importance_exposures,
  file.path(tables_dir, "11_top_exposures_for_importance_figure.csv"),
  row.names = FALSE
)
write.csv(
  shap_plot_data |>
    select(-model_feature_key),
  file.path(tables_dir, "12_top_exposure_shap_plot_values.csv"),
  row.names = FALSE
)
write.csv(
  calibration_by_decile,
  file.path(tables_dir, "13_test_calibration_by_decile.csv"),
  row.names = FALSE
)

write.csv(
  elastic_net_predictions,
  file.path(predictions_dir, "elastic_net_predictions.csv"),
  row.names = FALSE
)
write.csv(
  catboost_predictions,
  file.path(predictions_dir, "catboost_predictions.csv"),
  row.names = FALSE
)
write.csv(
  all_predictions,
  file.path(predictions_dir, "all_model_predictions.csv"),
  row.names = FALSE
)

ggsave(
  filename = file.path(figures_dir, "prediction_roc_pr_curves.png"),
  plot = performance_curve_plot,
  width = performance_figure_width,
  height = performance_figure_height,
  dpi = figure_dpi
)
ggsave(
  filename = file.path(figures_dir, "prediction_roc_pr_curves.pdf"),
  plot = performance_curve_plot,
  width = performance_figure_width,
  height = performance_figure_height,
  # cairo_pdf, not the default pdf device: the base device writes Type1
  # fonts and cannot encode UTF-8, so an em dash in a feature label came
  # out as "-" with an mbcsToSbcs warning. Units such as ug/m3 would fare
  # worse. PNG already uses cairo by default.
  device = cairo_pdf
)
ggsave(
  filename = file.path(figures_dir, "prediction_roc_auc_comparison.png"),
  plot = roc_auc_comparison_plot,
  width = 8,
  height = 7,
  dpi = figure_dpi
)
ggsave(
  filename = file.path(figures_dir, "prediction_roc_auc_comparison.pdf"),
  plot = roc_auc_comparison_plot,
  width = 8,
  height = 7,
  # cairo_pdf, not the default pdf device: the base device writes Type1
  # fonts and cannot encode UTF-8, so an em dash in a feature label came
  # out as "-" with an mbcsToSbcs warning. Units such as ug/m3 would fare
  # worse. PNG already uses cairo by default.
  device = cairo_pdf
)
ggsave(
  filename = file.path(figures_dir, "prediction_calibration.png"),
  plot = calibration_plot,
  width = 7,
  height = 6,
  dpi = figure_dpi
)
ggsave(
  filename = file.path(figures_dir, "prediction_calibration.pdf"),
  plot = calibration_plot,
  width = 7,
  height = 6,
  # cairo_pdf, not the default pdf device: the base device writes Type1
  # fonts and cannot encode UTF-8, so an em dash in a feature label came
  # out as "-" with an mbcsToSbcs warning. Units such as ug/m3 would fare
  # worse. PNG already uses cairo by default.
  device = cairo_pdf
)
ggsave(
  filename = file.path(figures_dir, "top10_exposure_shap_contributions.png"),
  plot = importance_beeswarm_plot,
  width = importance_figure_width,
  height = importance_figure_height,
  dpi = figure_dpi
)
ggsave(
  filename = file.path(figures_dir, "top10_exposure_shap_contributions.pdf"),
  plot = importance_beeswarm_plot,
  width = importance_figure_width,
  height = importance_figure_height,
  # cairo_pdf, not the default pdf device: the base device writes Type1
  # fonts and cannot encode UTF-8, so an em dash in a feature label came
  # out as "-" with an mbcsToSbcs warning. Units such as ug/m3 would fare
  # worse. PNG already uses cairo by default.
  device = cairo_pdf
)
ggsave(
  filename = file.path(figures_dir, "top10_exposure_mean_absolute_importance.png"),
  plot = importance_bar_plot,
  width = importance_figure_width,
  height = 7,
  dpi = figure_dpi
)
ggsave(
  filename = file.path(figures_dir, "top10_exposure_mean_absolute_importance.pdf"),
  plot = importance_bar_plot,
  width = importance_figure_width,
  height = 7,
  # cairo_pdf, not the default pdf device: the base device writes Type1
  # fonts and cannot encode UTF-8, so an em dash in a feature label came
  # out as "-" with an mbcsToSbcs warning. Units such as ug/m3 would fare
  # worse. PNG already uses cairo by default.
  device = cairo_pdf
)

saveRDS(
  list(
    settings = list(
      id_var = id_var,
      outcome_var = outcome_var,
      covariate_vars = covariate_vars,
      categorical_covariates = categorical_covariates,
      training_fraction = training_fraction,
      prediction_split_seed = prediction_split_seed,
      elastic_net_alpha_grid = elastic_net_alpha_grid,
      elastic_net_n_folds = elastic_net_n_folds,
      elastic_net_fold_seed = elastic_net_fold_seed,
      catboost_validation_fraction = catboost_validation_fraction,
      catboost_random_seed = catboost_random_seed,
      catboost_grid = catboost_grid,
      catboost_max_iterations = catboost_max_iterations,
      catboost_od_wait = catboost_od_wait,
      shap_max_rows = shap_max_rows,
      shap_seed = shap_seed,
      top_n_importance_exposures = top_n_importance_exposures
    ),
    predictor_vars = predictor_vars,
    eligible_exposure_vars = eligible_exposure_vars,
    predictor_manifest = predictor_manifest,
    exposure_qc = exposure_qc,
    split_assignment = split_assignment,
    preprocessing = preprocessing,
    matrix_feature_map = matrix_feature_map,
    shap_rows_PATID = dat[[id_var]][shap_rows],
    catboost_expected_value = catboost_expected_value
  ),
  file.path(rds_dir, "prediction_workflow_objects.rds"),
  compress = FALSE
)

capture.output(
  sessionInfo(),
  file = file.path(output_dir, "R_session_information.txt")
)

timestamp_message("Code File 3 completed. Outputs saved under: ", output_dir)
message("\nHeld-out testing performance:")
print(
  as.data.frame(
    model_metrics |>
      filter(analysis_set == "Testing") |>
      select(
        model,
        n,
        cases,
        prevalence,
        auroc,
        auprc,
        brier_score,
        calibration_intercept,
        calibration_slope
      )
  ),
  row.names = FALSE
)