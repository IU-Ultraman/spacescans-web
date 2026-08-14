# 2_ISEE26_workshop_attendee_exwas.R
# Corrected workflow: one full-sample MICE completion is created before the
# 50/50 split; MICE is not run separately in training and testing samples.
# Purpose:
#   Conduct a two-stage exposome-wide association study (ExWAS) for the
#   simulated binary outcome:
#     Stage 1: covariate-adjusted single-exposure logistic models in independent
#              50% training and 50% testing samples, with Bonferroni correction.
#     Stage 2: one covariate-adjusted multiexposure logistic model in the full
#              sample using exposures significant in both Stage 1 samples.
#
#   The script also performs exposure QC, reproducible correlation pruning,
#   standardization, one full-sample MICE imputation, ordinary logistic
#   regression, volcano plots, and workshop-ready supplemental tables.
#   The same single completed dataset is used for all downstream analyses.
#


rm(list = ls())

# -----------------------------------------------------------------------------
# Package check
# -----------------------------------------------------------------------------
required_packages <- c(
  "dplyr",
  "mice",
  "ggplot2"
)
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
  library(mice)
  library(ggplot2)
})

# =============================================================================
# USER SETTINGS: edit paths and analysis options here
# =============================================================================

# Current internal workshop directory.
# For GitHub Codespaces, change project_dir to the repository workspace path.
project_dir <- "/mnt/md0/Research Project/SPACESCANS/data/ISEE26Workshop"

attendee_dir <- file.path(project_dir, "forAttendee")
data_engineering_dir <- file.path(attendee_dir, "1_DataEngineering")

input_rds <- file.path(
  data_engineering_dir,
  "ISEE26_workshop_merged_exposome.rds"
)
exposure_manifest_csv <- file.path(
  data_engineering_dir,
  "exposure_variable_manifest.csv"
)

output_dir <- file.path(attendee_dir, "2_ExWAS")
tables_dir <- file.path(output_dir, "tables")
figures_dir <- file.path(output_dir, "figures")
rds_dir <- file.path(output_dir, "rds")

# Outcome, ID, and adjustment set.
id_var <- "PATID"
outcome_var <- "binary_outcome"
adjustment_covariates <- c("age", "sex", "race_eth")
categorical_covariates <- c("sex", "race_eth")

# Exposure QC settings.
# Binary exposures are retained when both groups meet minimum_binary_cell_count.
# The unique-value threshold is applied to nonbinary exposures.
unique_value_fraction_threshold <- 0.0001  # 0.01% of the analysis sample
minimum_continuous_unique <- 5L
minimum_binary_cell_count <- 20L
maximum_missing_fraction <- 0.80

# Correlation screening. A reproducible randomized greedy algorithm retains one
# member of each highly correlated set. Change the seed to obtain another valid
# random selection.
correlation_method <- "spearman"
correlation_threshold <- 0.99
correlation_seed <- 20260805

# Stage 1 split and multiplicity settings.
training_fraction <- 0.50
split_seed <- 20260801
alpha <- 0.05

# Per the requested rule, same effect direction is reported but not required by
# default. Change to TRUE if Stage 2 should also require concordant directions.
require_same_direction_for_stage2 <- FALSE

# Single-imputation settings. MICE is run once in the full sample with m = 1.
# The one completed dataset is used for training, testing, and Stage 2.
mice_m <- 1L
mice_maxit <- 5L
mice_seed <- 20260805
mice_quickpred_mincor <- 0.10
mice_quickpred_minpuc <- 0.25
use_outcome_as_imputation_predictor <- TRUE
mice_print_flag <- TRUE

# Saving the mids object can require substantial disk space.
save_mids_object <- FALSE

# Plot dimensions.
volcano_width <- 12
volcano_height <- 7
volcano_dpi <- 300

# This reference window is retained only for the supplemental QC table; it is
# not applied to any volcano plot.
volcano_focused_or_limits <- c(0.88, 1.12)
volcano_focused_or_breaks <- c(0.90, 0.95, 1.00, 1.05, 1.10)

# =============================================================================
# Helper functions
# =============================================================================

to_numeric_safely <- function(x) {
  if (is.numeric(x)) return(as.numeric(x))
  if (is.logical(x)) return(as.numeric(x))
  if (is.factor(x)) x <- as.character(x)
  suppressWarnings(as.numeric(x))
}

safe_quantile <- function(x, probability) {
  if (all(is.na(x))) return(NA_real_)
  as.numeric(quantile(x, probs = probability, na.rm = TRUE, names = FALSE))
}

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

make_exposure_summary <- function(dat, exposure_vars, manifest) {
  summary_rows <- lapply(exposure_vars, function(v) {
    x_original <- dat[[v]]
    x_numeric <- to_numeric_safely(x_original)
    conversion_failure_n <- sum(!is.na(x_original) & is.na(x_numeric))
    nonfinite_n <- sum(!is.na(x_numeric) & !is.finite(x_numeric))
    x_numeric[!is.finite(x_numeric)] <- NA_real_
    
    observed <- x_numeric[!is.na(x_numeric)]
    observed_values <- unique(observed)
    n_unique <- length(observed_values)
    binary_values <- if (n_unique == 2) sort(observed_values) else numeric(0)
    # A full frequency table can be large for continuous measures and is only
    # needed for the binary-cell-size check.
    cell_counts <- if (n_unique == 2) table(observed) else integer(0)
    
    data.frame(
      exposure = v,
      original_class = paste(class(x_original), collapse = "/"),
      n_total = length(x_numeric),
      n_nonmissing = sum(!is.na(x_numeric)),
      n_missing = sum(is.na(x_numeric)),
      missing_pct = 100 * mean(is.na(x_numeric)),
      conversion_failure_n = conversion_failure_n,
      nonfinite_to_missing_n = nonfinite_n,
      n_unique_nonmissing = n_unique,
      minimum_observed_cell_n = if (length(cell_counts) > 0) {
        min(as.integer(cell_counts))
      } else {
        NA_integer_
      },
      observed_min = if (length(observed) > 0) min(observed) else NA_real_,
      observed_q1 = safe_quantile(x_numeric, 0.25),
      observed_mean = if (length(observed) > 0) mean(observed) else NA_real_,
      observed_median = safe_quantile(x_numeric, 0.50),
      observed_q3 = safe_quantile(x_numeric, 0.75),
      observed_max = if (length(observed) > 0) max(observed) else NA_real_,
      observed_sd = if (length(observed) > 1) sd(observed) else NA_real_,
      lower_binary_value = if (n_unique == 2) binary_values[1] else NA_real_,
      higher_binary_value = if (n_unique == 2) binary_values[2] else NA_real_,
      stringsAsFactors = FALSE
    )
  })
  
  bind_rows(summary_rows) |>
    left_join(manifest, by = c("exposure" = "variable")) |>
    mutate(
      category = unname(source_to_category[source]),
      category = if_else(is.na(category), source, category),
      exposure_type = case_when(
        n_unique_nonmissing == 2 ~ "binary",
        n_unique_nonmissing > 2 ~ "continuous_or_count",
        TRUE ~ "degenerate"
      )
    ) |>
    arrange(category, exposure)
}

assign_exclusion_reasons <- function(exposure_summary, n_analysis) {
  continuous_unique_cutoff <- max(
    as.integer(minimum_continuous_unique),
    as.integer(ceiling(unique_value_fraction_threshold * n_analysis))
  )
  
  exposure_summary |>
    mutate(
      continuous_unique_cutoff = continuous_unique_cutoff,
      exclusion_reason = case_when(
        conversion_failure_n > 0 ~ "non_numeric_values",
        n_nonmissing == 0 ~ "all_missing",
        missing_pct / 100 > maximum_missing_fraction ~ "excessive_missingness",
        n_unique_nonmissing < 2 ~ "fewer_than_two_unique_values",
        exposure_type == "binary" &
          minimum_observed_cell_n < minimum_binary_cell_count ~
          "rare_binary_level",
        exposure_type != "binary" &
          n_unique_nonmissing < continuous_unique_cutoff ~
          "too_few_unique_values",
        is.na(observed_sd) | observed_sd == 0 ~ "zero_or_undefined_sd",
        TRUE ~ NA_character_
      ),
      eligible_after_unique_value_qc = is.na(exclusion_reason)
    )
}

prepare_and_scale_exposures <- function(dat, exposure_summary, exposure_vars) {
  out <- dat
  scaling_rows <- vector("list", length(exposure_vars))
  
  for (i in seq_along(exposure_vars)) {
    v <- exposure_vars[i]
    info <- exposure_summary[exposure_summary$exposure == v, , drop = FALSE]
    x <- to_numeric_safely(out[[v]])
    x[!is.finite(x)] <- NA_real_
    
    if (info$exposure_type == "binary") {
      low <- info$lower_binary_value
      high <- info$higher_binary_value
      x <- ifelse(is.na(x), NA_real_, ifelse(x == high, 1, 0))
      
      scaling_rows[[i]] <- data.frame(
        exposure = v,
        transformation = "binary_recode",
        centering_mean = NA_real_,
        scaling_sd = NA_real_,
        original_lower_value = low,
        original_higher_value = high,
        analysis_unit = "Higher versus lower observed value",
        stringsAsFactors = FALSE
      )
    } else {
      mu <- mean(x, na.rm = TRUE)
      sigma <- sd(x, na.rm = TRUE)
      x <- (x - mu) / sigma
      
      scaling_rows[[i]] <- data.frame(
        exposure = v,
        transformation = "z_score",
        centering_mean = mu,
        scaling_sd = sigma,
        original_lower_value = NA_real_,
        original_higher_value = NA_real_,
        analysis_unit = "Per 1 SD increase",
        stringsAsFactors = FALSE
      )
    }
    
    out[[v]] <- x
  }
  
  list(data = out, scaling = bind_rows(scaling_rows))
}

compute_high_correlation_pairs <- function(dat, exposure_vars) {
  if (length(exposure_vars) < 2) {
    return(list(
      correlation_matrix = matrix(
        1,
        nrow = length(exposure_vars),
        ncol = length(exposure_vars),
        dimnames = list(exposure_vars, exposure_vars)
      ),
      high_pairs = data.frame(
        exposure_1 = character(),
        exposure_2 = character(),
        correlation = numeric(),
        absolute_correlation = numeric(),
        stringsAsFactors = FALSE
      )
    ))
  }
  
  correlation_matrix <- suppressWarnings(cor(
    dat[exposure_vars],
    use = "pairwise.complete.obs",
    method = correlation_method
  ))
  
  high_index <- which(
    upper.tri(correlation_matrix) &
      is.finite(correlation_matrix) &
      abs(correlation_matrix) >= correlation_threshold,
    arr.ind = TRUE
  )
  
  if (nrow(high_index) == 0) {
    high_pairs <- data.frame(
      exposure_1 = character(),
      exposure_2 = character(),
      correlation = numeric(),
      absolute_correlation = numeric(),
      stringsAsFactors = FALSE
    )
  } else {
    high_pairs <- data.frame(
      exposure_1 = rownames(correlation_matrix)[high_index[, "row"]],
      exposure_2 = colnames(correlation_matrix)[high_index[, "col"]],
      correlation = correlation_matrix[high_index],
      stringsAsFactors = FALSE
    ) |>
      mutate(absolute_correlation = abs(correlation)) |>
      arrange(desc(absolute_correlation), exposure_1, exposure_2)
  }
  
  list(
    correlation_matrix = correlation_matrix,
    high_pairs = high_pairs
  )
}

random_greedy_correlation_pruning <- function(
    exposure_vars,
    correlation_matrix,
    threshold,
    seed
) {
  set.seed(seed)
  random_order <- sample(exposure_vars, length(exposure_vars), replace = FALSE)
  random_priority <- setNames(seq_along(random_order), random_order)
  
  retained <- character()
  decision_rows <- list()
  
  for (v in random_order) {
    if (length(retained) == 0) {
      retained <- c(retained, v)
      next
    }
    
    correlations <- correlation_matrix[v, retained]
    conflicting <- retained[
      is.finite(correlations) & abs(correlations) >= threshold
    ]
    
    if (length(conflicting) == 0) {
      retained <- c(retained, v)
    } else {
      blocker_correlations <- correlation_matrix[v, conflicting]
      blocker <- conflicting[which.max(abs(blocker_correlations))]
      
      decision_rows[[length(decision_rows) + 1L]] <- data.frame(
        excluded_exposure = v,
        retained_exposure = blocker,
        correlation = unname(correlation_matrix[v, blocker]),
        absolute_correlation = abs(unname(correlation_matrix[v, blocker])),
        excluded_random_priority = unname(random_priority[v]),
        retained_random_priority = unname(random_priority[blocker]),
        reason = paste0("absolute_correlation_at_least_", threshold),
        stringsAsFactors = FALSE
      )
    }
  }
  
  decisions <- if (length(decision_rows) > 0) {
    bind_rows(decision_rows) |>
      arrange(excluded_random_priority)
  } else {
    data.frame(
      excluded_exposure = character(),
      retained_exposure = character(),
      correlation = numeric(),
      absolute_correlation = numeric(),
      excluded_random_priority = integer(),
      retained_random_priority = integer(),
      reason = character(),
      stringsAsFactors = FALSE
    )
  }
  
  priority_table <- data.frame(
    exposure = exposure_vars,
    random_priority = unname(random_priority[exposure_vars]),
    correlation_filter_status = ifelse(
      exposure_vars %in% retained,
      "retained",
      "excluded"
    ),
    stringsAsFactors = FALSE
  ) |>
    arrange(random_priority)
  
  list(
    retained = retained,
    excluded = setdiff(exposure_vars, retained),
    decisions = decisions,
    priority_table = priority_table
  )
}

annotate_high_pairs <- function(high_pairs, pruning) {
  if (nrow(high_pairs) == 0) return(high_pairs)
  
  status_lookup <- setNames(
    pruning$priority_table$correlation_filter_status,
    pruning$priority_table$exposure
  )
  
  high_pairs |>
    mutate(
      exposure_1_status = unname(status_lookup[exposure_1]),
      exposure_2_status = unname(status_lookup[exposure_2]),
      retained_exposure = case_when(
        exposure_1_status == "retained" & exposure_2_status == "excluded" ~
          exposure_1,
        exposure_2_status == "retained" & exposure_1_status == "excluded" ~
          exposure_2,
        TRUE ~ NA_character_
      ),
      excluded_exposure = case_when(
        exposure_1_status == "excluded" & exposure_2_status == "retained" ~
          exposure_1,
        exposure_2_status == "excluded" & exposure_1_status == "retained" ~
          exposure_2,
        TRUE ~ NA_character_
      ),
      pair_decision = case_when(
        !is.na(retained_exposure) ~ "one_retained_one_excluded",
        exposure_1_status == "excluded" & exposure_2_status == "excluded" ~
          "both_excluded_by_random_greedy_filter",
        TRUE ~ "review"
      )
    )
}

check_split_eligibility <- function(training_dat, testing_dat, exposure_vars) {
  bind_rows(lapply(exposure_vars, function(v) {
    train_values <- training_dat[[v]][!is.na(training_dat[[v]])]
    test_values <- testing_dat[[v]][!is.na(testing_dat[[v]])]
    
    data.frame(
      exposure = v,
      training_n_nonmissing = length(train_values),
      training_n_unique = length(unique(train_values)),
      testing_n_nonmissing = length(test_values),
      testing_n_unique = length(unique(test_values)),
      eligible_in_both_splits =
        length(unique(train_values)) >= 2 &&
        length(unique(test_values)) >= 2,
      stringsAsFactors = FALSE
    )
  }))
}

make_single_imputed_dataset <- function(dat, exposure_vars, seed, data_label) {
  model_vars <- unique(c(outcome_var, adjustment_covariates, exposure_vars))
  frame <- dat[model_vars]
  
  if (anyDuplicated(names(frame))) {
    stop("Duplicate variables in the ", data_label, " MICE frame.")
  }
  
  all_missing <- names(frame)[vapply(frame, function(x) all(is.na(x)), logical(1))]
  if (length(all_missing) > 0) {
    stop(
      "The ", data_label, " MICE frame contains all-missing variables: ",
      paste(all_missing, collapse = ", ")
    )
  }
  
  missing_cells <- sum(is.na(frame))
  message(
    "Preparing ", data_label, " MICE data: n=", nrow(frame),
    "; variables=", ncol(frame),
    "; missing cells=", missing_cells
  )
  
  if (missing_cells == 0) {
    return(list(
      mids = NULL,
      completed = frame,
      method = setNames(rep("", ncol(frame)), names(frame)),
      predictor_matrix = matrix(
        0,
        nrow = ncol(frame),
        ncol = ncol(frame),
        dimnames = list(names(frame), names(frame))
      ),
      missing_cells = 0,
      logged_events = NULL
    ))
  }
  
  # Select default imputation methods without running a preliminary MICE model.
  method <- mice::make.method(frame)
  
  # The outcome is observed and is never imputed.
  method[outcome_var] <- ""
  
  predictor_matrix <- mice::quickpred(
    frame,
    mincor = mice_quickpred_mincor,
    minpuc = mice_quickpred_minpuc
  )
  predictor_matrix[outcome_var, ] <- 0
  
  # The observed outcome may be used to predict missing covariates/exposures.
  if (isTRUE(use_outcome_as_imputation_predictor)) {
    predictor_matrix[, outcome_var] <- 1
    predictor_matrix[outcome_var, outcome_var] <- 0
  } else {
    predictor_matrix[, outcome_var] <- 0
  }
  
  incomplete_targets <- names(method)[method != ""]
  covariates_present <- intersect(adjustment_covariates, names(frame))
  if (length(incomplete_targets) > 0 && length(covariates_present) > 0) {
    predictor_matrix[incomplete_targets, covariates_present] <- 1
  }
  diag(predictor_matrix) <- 0
  
  imp <- mice::mice(
    frame,
    m = mice_m,
    maxit = mice_maxit,
    method = method,
    predictorMatrix = predictor_matrix,
    seed = seed,
    printFlag = mice_print_flag
  )
  
  completed <- mice::complete(imp, action = 1)
  
  remaining_missing <- colSums(is.na(completed))
  if (any(remaining_missing > 0)) {
    stop(
      "The single MICE completion left missing values in: ",
      paste(names(remaining_missing)[remaining_missing > 0], collapse = ", ")
    )
  }
  
  list(
    mids = imp,
    completed = completed,
    method = method,
    predictor_matrix = predictor_matrix,
    missing_cells = missing_cells,
    logged_events = imp$loggedEvents
  )
}

ordinary_glm_summary <- function(analysis_data, model_formula) {
  fit <- tryCatch(
    glm(
      formula = model_formula,
      data = analysis_data,
      family = binomial(link = "logit")
    ),
    error = function(e) e
  )
  
  if (inherits(fit, "error")) {
    return(list(
      ok = FALSE,
      error = conditionMessage(fit),
      summary = NULL,
      n_model = NA_integer_,
      degrees_freedom = NA_real_,
      converged = FALSE
    ))
  }
  
  coefficient_matrix <- summary(fit)$coefficients
  model_summary <- data.frame(
    term = rownames(coefficient_matrix),
    estimate = coefficient_matrix[, "Estimate"],
    std.error = coefficient_matrix[, "Std. Error"],
    statistic = coefficient_matrix[, "z value"],
    p.value = coefficient_matrix[, "Pr(>|z|)"],
    stringsAsFactors = FALSE,
    row.names = NULL
  )
  model_summary$conf_low <-
    model_summary$estimate - qnorm(0.975) * model_summary$std.error
  model_summary$conf_high <-
    model_summary$estimate + qnorm(0.975) * model_summary$std.error
  model_summary$term_clean <- gsub(
    "\\x60",
    "",
    model_summary$term,
    perl = TRUE
  )
  
  list(
    ok = TRUE,
    error = NA_character_,
    summary = model_summary,
    n_model = stats::nobs(fit),
    degrees_freedom = fit$df.residual,
    converged = isTRUE(fit$converged)
  )
}

fit_one_exposure <- function(exposure, analysis_data, split_label) {
  model_formula <- reformulate(
    termlabels = c(exposure, adjustment_covariates),
    response = outcome_var
  )
  
  model_fit <- ordinary_glm_summary(analysis_data, model_formula)
  
  if (!model_fit$ok) {
    return(data.frame(
      exposure = exposure,
      split = split_label,
      beta = NA_real_,
      standard_error = NA_real_,
      OR = NA_real_,
      CI_95_lower = NA_real_,
      CI_95_upper = NA_real_,
      p_value = NA_real_,
      degrees_freedom = NA_real_,
      n_model = model_fit$n_model,
      n_imputations = 1L,
      model_converged = FALSE,
      model_status = "failed",
      model_error = model_fit$error,
      stringsAsFactors = FALSE
    ))
  }
  
  exposure_row <- model_fit$summary |>
    filter(term_clean == exposure)
  
  if (nrow(exposure_row) != 1) {
    return(data.frame(
      exposure = exposure,
      split = split_label,
      beta = NA_real_,
      standard_error = NA_real_,
      OR = NA_real_,
      CI_95_lower = NA_real_,
      CI_95_upper = NA_real_,
      p_value = NA_real_,
      degrees_freedom = model_fit$degrees_freedom,
      n_model = model_fit$n_model,
      n_imputations = 1L,
      model_converged = model_fit$converged,
      model_status = "failed",
      model_error = paste0(
        "Expected one model term named '", exposure,
        "' but found ", nrow(exposure_row), "."
      ),
      stringsAsFactors = FALSE
    ))
  }
  
  data.frame(
    exposure = exposure,
    split = split_label,
    beta = exposure_row$estimate,
    standard_error = exposure_row$std.error,
    OR = exp(exposure_row$estimate),
    CI_95_lower = exp(exposure_row$conf_low),
    CI_95_upper = exp(exposure_row$conf_high),
    p_value = exposure_row$p.value,
    degrees_freedom = model_fit$degrees_freedom,
    n_model = model_fit$n_model,
    n_imputations = 1L,
    model_converged = model_fit$converged,
    model_status = "ok",
    model_error = NA_character_,
    stringsAsFactors = FALSE
  )
}

run_stage1_models <- function(analysis_data, exposure_vars, split_label) {
  result_rows <- vector("list", length(exposure_vars))
  
  for (i in seq_along(exposure_vars)) {
    v <- exposure_vars[i]
    result_rows[[i]] <- fit_one_exposure(
      exposure = v,
      analysis_data = analysis_data,
      split_label = split_label
    )
    
    if (i == 1 || i %% 10 == 0 || i == length(exposure_vars)) {
      message(
        "Stage 1 ", split_label, ": completed ",
        i, " of ", length(exposure_vars), " exposure models."
      )
    }
  }
  
  results <- bind_rows(result_rows)
  n_tests <- length(exposure_vars)
  
  results |>
    mutate(
      n_stage1_tests = n_tests,
      bonferroni_raw_p_threshold = alpha / n_tests,
      p_bonferroni = pmin(1, p_value * n_tests),
      bonferroni_significant =
        model_status == "ok" &
        !is.na(p_bonferroni) &
        p_bonferroni < alpha
    )
}

fit_stage2_model <- function(analysis_data, exposure_vars) {
  if (length(exposure_vars) == 0) {
    return(data.frame(
      exposure = character(),
      beta = numeric(),
      standard_error = numeric(),
      OR = numeric(),
      CI_95_lower = numeric(),
      CI_95_upper = numeric(),
      p_value = numeric(),
      degrees_freedom = numeric(),
      n_model = integer(),
      n_imputations = integer(),
      model_converged = logical(),
      model_status = character(),
      model_error = character(),
      stringsAsFactors = FALSE
    ))
  }
  
  model_formula <- reformulate(
    termlabels = c(exposure_vars, adjustment_covariates),
    response = outcome_var
  )
  model_fit <- ordinary_glm_summary(analysis_data, model_formula)
  
  if (!model_fit$ok) {
    return(data.frame(
      exposure = exposure_vars,
      beta = NA_real_,
      standard_error = NA_real_,
      OR = NA_real_,
      CI_95_lower = NA_real_,
      CI_95_upper = NA_real_,
      p_value = NA_real_,
      degrees_freedom = NA_real_,
      n_model = model_fit$n_model,
      n_imputations = 1L,
      model_converged = FALSE,
      model_status = "failed",
      model_error = model_fit$error,
      stringsAsFactors = FALSE
    ))
  }
  
  exposure_rows <- model_fit$summary |>
    filter(term_clean %in% exposure_vars) |>
    transmute(
      exposure = term_clean,
      beta = estimate,
      standard_error = std.error,
      OR = exp(estimate),
      CI_95_lower = exp(conf_low),
      CI_95_upper = exp(conf_high),
      p_value = p.value,
      degrees_freedom = model_fit$degrees_freedom,
      n_model = model_fit$n_model,
      n_imputations = 1L,
      model_converged = model_fit$converged,
      model_status = "ok",
      model_error = NA_character_
    )
  
  missing_terms <- setdiff(exposure_vars, exposure_rows$exposure)
  if (length(missing_terms) > 0) {
    exposure_rows <- bind_rows(
      exposure_rows,
      data.frame(
        exposure = missing_terms,
        beta = NA_real_,
        standard_error = NA_real_,
        OR = NA_real_,
        CI_95_lower = NA_real_,
        CI_95_upper = NA_real_,
        p_value = NA_real_,
        degrees_freedom = model_fit$degrees_freedom,
        n_model = model_fit$n_model,
        n_imputations = 1L,
        model_converged = model_fit$converged,
        model_status = "failed",
        model_error = "Exposure coefficient was not estimable in the model.",
        stringsAsFactors = FALSE
      )
    )
  }
  
  exposure_rows |>
    arrange(match(exposure, exposure_vars))
}

make_volcano_plot <- function(
    plot_dat,
    facet = TRUE,
    x_lab = "Adjusted Odds Ratio",
    y_lab = "-log10(p-value)",
    focused_or_limits = NULL,
    focused_or_breaks = NULL
) {
  # Retain model results that can be displayed on the volcano plot.
  plot_dat <- plot_dat |>
    filter(
      model_status == "ok",
      is.finite(OR),
      OR > 0,
      is.finite(p_value),
      p_value >= 0,
      p_value <= 1
    ) |>
    mutate(
      category = if_else(
        is.na(category) | category == "",
        "Other/Unknown",
        as.character(category)
      ),
      negative_log10_p = -log10(
        pmax(p_value, .Machine$double.xmin)
      )
    )
  
  if (nrow(plot_dat) == 0) {
    return(NULL)
  }
  
  # Follow the C6 figure style: show significant/total counts in the category
  # legend and use the Dark 3 qualitative color palette.
  category_legend_stats <- plot_dat |>
    group_by(category) |>
    summarise(
      n_total = n(),
      n_significant = sum(
        bonferroni_significant,
        na.rm = TRUE
      ),
      .groups = "drop"
    ) |>
    arrange(category) |>
    mutate(
      category_legend = sprintf(
        "%s (%d/%d)",
        category,
        n_significant,
        n_total
      )
    )
  
  category_legend_lookup <- setNames(
    category_legend_stats$category_legend,
    category_legend_stats$category
  )
  category_legend_levels <-
    category_legend_stats$category_legend
  
  plot_dat <- plot_dat |>
    mutate(
      category_legend = factor(
        unname(category_legend_lookup[category]),
        levels = category_legend_levels
      )
    )
  
  category_colors <- setNames(
    grDevices::hcl.colors(
      length(category_legend_levels),
      palette = "Dark 3"
    ),
    category_legend_levels
  )
  
  bonferroni_cutoff <- -log10(
    alpha / unique(plot_dat$n_stage1_tests)[1]
  )
  
  if (is.null(focused_or_breaks)) {
    volcano_x_scale <- scale_x_continuous(trans = "log10")
  } else {
    volcano_x_scale <- scale_x_continuous(
      trans = "log10",
      breaks = focused_or_breaks
    )
  }
  
  volcano_plot <- ggplot(
    plot_dat,
    aes(x = OR, y = negative_log10_p)
  ) +
    geom_point(
      aes(color = category_legend),
      alpha = 0.80,
      size = 2.0
    ) +
    geom_hline(
      yintercept = bonferroni_cutoff,
      linetype = "dashed",
      linewidth = 0.6
    ) +
    scale_color_manual(
      values = category_colors,
      drop = FALSE,
      guide = guide_legend(order = 1)
    ) +
    volcano_x_scale +
    labs(
      x = x_lab,
      y = y_lab,
      color = "Category (significant/total)"
    ) +
    theme_bw() +
    theme(
      panel.grid.major = element_line(linewidth = 0.2),
      panel.grid.minor = element_line(linewidth = 0.15),
      axis.text = element_text(size = 11, face = "bold"),
      axis.title = element_text(size = 12, face = "bold"),
      legend.title = element_text(size = 11, face = "bold"),
      legend.text = element_text(size = 10),
      legend.key.height = grid::unit(0.9, "lines")
    )
  
  # coord_cartesian changes only the visible window. Points outside the window
  # stay in plot_dat, category counts, significance counts, and result tables.
  if (!is.null(focused_or_limits)) {
    volcano_plot <- volcano_plot +
      coord_cartesian(xlim = focused_or_limits)
  }
  
  if (isTRUE(facet)) {
    volcano_plot <- volcano_plot +
      facet_wrap(~split, nrow = 1)
  }
  
  volcano_plot
}

# =============================================================================
# 1) Import and validate the merged workshop dataset
# =============================================================================

dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(tables_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(figures_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(rds_dir, showWarnings = FALSE, recursive = TRUE)

if (!file.exists(input_rds)) {
  stop("Merged input RDS does not exist. Run Code File 1 first: ", input_rds)
}
if (!file.exists(exposure_manifest_csv)) {
  stop(
    "Exposure manifest does not exist. Run Code File 1 first: ",
    exposure_manifest_csv
  )
}

if (training_fraction <= 0 || training_fraction >= 1) {
  stop("training_fraction must be strictly between 0 and 1.")
}
if (correlation_threshold <= 0 || correlation_threshold > 1) {
  stop("correlation_threshold must be in (0, 1].")
}
if (!correlation_method %in% c("pearson", "spearman", "kendall")) {
  stop("correlation_method must be pearson, spearman, or kendall.")
}
if (mice_m != 1) {
  stop("This workshop script requires exactly one MICE imputation: mice_m = 1.")
}

message("Reading merged workshop dataset: ", input_rds)
dat <- readRDS(input_rds)
if (inherits(dat, "sf")) {
  if (!requireNamespace("sf", quietly = TRUE)) {
    stop("Package 'sf' is required to drop geometry from an sf input RDS.")
  }
  dat <- sf::st_drop_geometry(dat)
}
dat <- as.data.frame(dat)

manifest <- read.csv(
  exposure_manifest_csv,
  stringsAsFactors = FALSE,
  check.names = FALSE
)

required_manifest_cols <- c("variable", "source")
missing_manifest_cols <- setdiff(required_manifest_cols, names(manifest))
if (length(missing_manifest_cols) > 0) {
  stop(
    "Exposure manifest is missing columns: ",
    paste(missing_manifest_cols, collapse = ", ")
  )
}

manifest <- manifest |>
  distinct(variable, .keep_all = TRUE)
exposure_vars_manifest <- manifest$variable

required_analysis_vars <- unique(c(
  id_var,
  outcome_var,
  adjustment_covariates,
  exposure_vars_manifest
))
missing_analysis_vars <- setdiff(required_analysis_vars, names(dat))
if (length(missing_analysis_vars) > 0) {
  stop(
    "Merged dataset is missing required variables: ",
    paste(missing_analysis_vars, collapse = ", ")
  )
}

dat[[id_var]] <- as.character(dat[[id_var]])
if (anyNA(dat[[id_var]]) || any(dat[[id_var]] == "")) {
  stop(id_var, " contains missing or blank values.")
}
if (anyDuplicated(dat[[id_var]])) {
  stop(id_var, " must be unique for the random train/test split.")
}

outcome_original <- dat[[outcome_var]]
dat[[outcome_var]] <- to_numeric_safely(outcome_original)
if (any(!is.na(outcome_original) & is.na(dat[[outcome_var]]))) {
  stop(outcome_var, " contains nonnumeric values that could not be converted.")
}
dat[[outcome_var]][!is.finite(dat[[outcome_var]])] <- NA_real_

n_missing_outcome <- sum(is.na(dat[[outcome_var]]))
if (n_missing_outcome > 0) {
  warning("Dropping ", n_missing_outcome, " records with missing outcome.")
  dat <- dat[!is.na(dat[[outcome_var]]), , drop = FALSE]
}

outcome_values <- sort(unique(dat[[outcome_var]]))
if (!identical(outcome_values, c(0, 1))) {
  stop(
    outcome_var,
    " must contain both numeric values 0 and 1. Observed values: ",
    paste(outcome_values, collapse = ", ")
  )
}

numeric_covariates <- setdiff(adjustment_covariates, categorical_covariates)
for (v in numeric_covariates) {
  original <- dat[[v]]
  converted <- to_numeric_safely(original)
  if (any(!is.na(original) & is.na(converted))) {
    stop("Adjustment covariate ", v, " contains nonnumeric values.")
  }
  converted[!is.finite(converted)] <- NA_real_
  dat[[v]] <- converted
}

for (v in intersect(categorical_covariates, adjustment_covariates)) {
  dat[[v]] <- factor(dat[[v]])
  if (nlevels(droplevels(dat[[v]])) < 2) {
    stop("Categorical adjustment covariate ", v, " has fewer than two levels.")
  }
}

message(
  "Analysis sample: n=", nrow(dat),
  "; cases=", sum(dat[[outcome_var]] == 1),
  "; outcome prevalence=", round(mean(dat[[outcome_var]]), 4)
)

# =============================================================================
# 2) Exposure QC, summaries, and transformations
# =============================================================================

message("Computing exposure summaries and unique-value QC...")
exposure_summary <- make_exposure_summary(
  dat = dat,
  exposure_vars = exposure_vars_manifest,
  manifest = manifest
) |>
  assign_exclusion_reasons(n_analysis = nrow(dat))

eligible_after_unique_qc <- exposure_summary |>
  filter(eligible_after_unique_value_qc) |>
  pull(exposure)

if (length(eligible_after_unique_qc) == 0) {
  stop("No exposures remained after unique-value and missingness QC.")
}

message(
  "Exposure QC: ", length(eligible_after_unique_qc), " of ",
  length(exposure_vars_manifest), " exposures retained before correlation screening."
)

# Estimate each transformation once in the full observed sample so training,
# testing, and Stage 2 odds ratios use the same exposure scale. No outcome
# information is used to calculate these scaling parameters.
prepared <- prepare_and_scale_exposures(
  dat = dat,
  exposure_summary = exposure_summary,
  exposure_vars = eligible_after_unique_qc
)
analysis_dat <- prepared$data
scaling_parameters <- prepared$scaling |>
  left_join(
    exposure_summary |>
      select(exposure, source, category, exposure_type),
    by = "exposure"
  ) |>
  arrange(category, exposure)

# =============================================================================
# 3) Pairwise correlations and reproducible randomized pruning
# =============================================================================

message(
  "Computing ", correlation_method,
  " pairwise correlations across ",
  length(eligible_after_unique_qc), " eligible exposures..."
)
correlation_results <- compute_high_correlation_pairs(
  dat = analysis_dat,
  exposure_vars = eligible_after_unique_qc
)

correlation_pruning <- random_greedy_correlation_pruning(
  exposure_vars = eligible_after_unique_qc,
  correlation_matrix = correlation_results$correlation_matrix,
  threshold = correlation_threshold,
  seed = correlation_seed
)

high_correlation_pairs <- annotate_high_pairs(
  correlation_results$high_pairs,
  correlation_pruning
)

correlation_decisions <- correlation_pruning$decisions |>
  left_join(
    exposure_summary |>
      select(excluded_exposure = exposure, excluded_source = source),
    by = "excluded_exposure"
  ) |>
  left_join(
    exposure_summary |>
      select(retained_exposure = exposure, retained_source = source),
    by = "retained_exposure"
  )

message(
  "Correlation screening: high-correlation pairs=", nrow(high_correlation_pairs),
  "; excluded exposures=", length(correlation_pruning$excluded),
  "; retained exposures=", length(correlation_pruning$retained)
)

# =============================================================================
# 4) Create one full-sample, single-imputed dataset
# =============================================================================

# Exposure statistics, unique-value QC, transformations, and correlations above
# all used the original pre-imputation data. Only now do we impute.
message("Running one full-sample MICE imputation with m = 1...")

single_imputation <- make_single_imputed_dataset(
  dat = analysis_dat,
  exposure_vars = correlation_pruning$retained,
  seed = mice_seed,
  data_label = "full sample"
)

# This is the one completed dataset used in every downstream model.
imputed_dat <- single_imputation$completed

if (nrow(imputed_dat) != nrow(analysis_dat)) {
  stop("Single imputation changed the number of analysis rows.")
}

# Retain PATID in the saved completed dataset, but not in any model.
single_imputed_output <- imputed_dat
single_imputed_output[[id_var]] <- analysis_dat[[id_var]]
single_imputed_output <- single_imputed_output |>
  select(all_of(id_var), everything())

# =============================================================================
# 5) Random 50/50 split of the single-imputed dataset
# =============================================================================

set.seed(split_seed)
n_training <- floor(training_fraction * nrow(imputed_dat))
training_index <- sample.int(
  n = nrow(imputed_dat),
  size = n_training,
  replace = FALSE
)
testing_index <- setdiff(seq_len(nrow(imputed_dat)), training_index)

training_dat <- imputed_dat[training_index, , drop = FALSE]
testing_dat <- imputed_dat[testing_index, , drop = FALSE]

split_assignment <- data.frame(
  PATID = analysis_dat[[id_var]],
  split = ifelse(
    seq_len(nrow(analysis_dat)) %in% training_index,
    "Training",
    "Testing"
  ),
  stringsAsFactors = FALSE
)
names(split_assignment)[1] <- id_var

split_summary <- bind_rows(
  data.frame(
    split = "Full sample",
    n = nrow(imputed_dat),
    cases = sum(imputed_dat[[outcome_var]] == 1),
    outcome_prevalence = mean(imputed_dat[[outcome_var]]),
    stringsAsFactors = FALSE
  ),
  data.frame(
    split = "Discovery",
    n = nrow(training_dat),
    cases = sum(training_dat[[outcome_var]] == 1),
    outcome_prevalence = mean(training_dat[[outcome_var]]),
    stringsAsFactors = FALSE
  ),
  data.frame(
    split = "Replication",
    n = nrow(testing_dat),
    cases = sum(testing_dat[[outcome_var]] == 1),
    outcome_prevalence = mean(testing_dat[[outcome_var]]),
    stringsAsFactors = FALSE
  )
)

split_eligibility <- check_split_eligibility(
  training_dat = training_dat,
  testing_dat = testing_dat,
  exposure_vars = correlation_pruning$retained
)

stage1_exposures <- split_eligibility |>
  filter(eligible_in_both_splits) |>
  pull(exposure)

split_excluded_exposures <- split_eligibility |>
  filter(!eligible_in_both_splits) |>
  pull(exposure)

if (length(stage1_exposures) == 0) {
  stop("No exposures remained eligible in both the discovery and replication samples.")
}

message(
  "Stage 1 will test ", length(stage1_exposures),
  " exposures in each split; Bonferroni raw-p threshold=",
  signif(alpha / length(stage1_exposures), 4)
)

# Update the all-exposure QC table with correlation and split decisions.
exposure_qc <- exposure_summary |>
  left_join(correlation_pruning$priority_table, by = "exposure") |>
  left_join(split_eligibility, by = "exposure") |>
  mutate(
    correlation_filter_status = case_when(
      !eligible_after_unique_value_qc ~ "not_assessed",
      is.na(correlation_filter_status) ~ "not_assessed",
      TRUE ~ correlation_filter_status
    ),
    final_exclusion_reason = case_when(
      !is.na(exclusion_reason) ~ exclusion_reason,
      correlation_filter_status == "excluded" ~ "high_pairwise_correlation",
      !is.na(eligible_in_both_splits) & !eligible_in_both_splits ~
        "insufficient_unique_values_in_discovery_or_replication",
      TRUE ~ NA_character_
    ),
    included_in_stage1 = exposure %in% stage1_exposures
  ) |>
  arrange(category, exposure)

# =============================================================================
# 6) Stage 1: single-exposure logistic regression in both splits
# =============================================================================

message("Fitting Stage 1 single-exposure models in the training sample...")
stage1_training <- run_stage1_models(
  analysis_data = training_dat,
  exposure_vars = stage1_exposures,
  split_label = "Training"
)

message("Fitting Stage 1 single-exposure models in the testing sample...")
stage1_testing <- run_stage1_models(
  analysis_data = testing_dat,
  exposure_vars = stage1_exposures,
  split_label = "Testing"
)

training_wide <- stage1_training |>
  select(-split) |>
  rename_with(
    ~ paste0(.x, "_training"),
    -exposure
  )

testing_wide <- stage1_testing |>
  select(-split) |>
  rename_with(
    ~ paste0(.x, "_testing"),
    -exposure
  )

stage1_combined <- full_join(
  training_wide,
  testing_wide,
  by = "exposure"
) |>
  mutate(
    significant_in_both_splits =
      bonferroni_significant_training &
      bonferroni_significant_testing,
    same_effect_direction = case_when(
      is.na(beta_training) | is.na(beta_testing) ~ NA,
      TRUE ~ sign(beta_training) == sign(beta_testing)
    ),
    selected_for_stage2 =
      significant_in_both_splits &
      (
        !require_same_direction_for_stage2 |
          (!is.na(same_effect_direction) & same_effect_direction)
      )
  )

stage2_exposures <- stage1_combined |>
  filter(selected_for_stage2) |>
  pull(exposure)

message(
  "Stage 1 results: training Bonferroni hits=",
  sum(stage1_training$bonferroni_significant, na.rm = TRUE),
  "; testing Bonferroni hits=",
  sum(stage1_testing$bonferroni_significant, na.rm = TRUE),
  "; selected for Stage 2=", length(stage2_exposures)
)

# Tables combining original-scale descriptive statistics with model results.
summary_columns_for_results <- exposure_summary |>
  select(
    exposure,
    source,
    category,
    exposure_type,
    n_total,
    n_nonmissing,
    n_missing,
    missing_pct,
    n_unique_nonmissing,
    observed_min,
    observed_q1,
    observed_mean,
    observed_median,
    observed_q3,
    observed_max,
    observed_sd,
    lower_binary_value,
    higher_binary_value
  ) |>
  left_join(
    scaling_parameters |>
      select(exposure, transformation, analysis_unit),
    by = "exposure"
  )

stage1_results_with_summary <- summary_columns_for_results |>
  filter(exposure %in% stage1_exposures) |>
  left_join(stage1_combined, by = "exposure") |>
  arrange(category, exposure)

stage1_selected_for_stage2 <- stage1_results_with_summary |>
  filter(selected_for_stage2)

# =============================================================================
# 7) Stage 2: full-sample multiexposure logistic regression
# =============================================================================

if (length(stage2_exposures) > 0) {
  message(
    "Fitting the Stage 2 multiexposure model in the same single-imputed ",
    "full dataset for ", length(stage2_exposures), " exposures..."
  )
  
  stage2_results <- fit_stage2_model(
    analysis_data = imputed_dat,
    exposure_vars = stage2_exposures
  )
} else {
  message(
    "No exposure was Bonferroni significant in both Stage 1 splits; ",
    "the Stage 2 model will not be fitted."
  )
  
  stage2_results <- fit_stage2_model(
    analysis_data = imputed_dat,
    exposure_vars = character()
  )
}

# Flag nominally significant Stage 2 coefficients and count them.
# This p < 0.05 threshold is applied to the mutually adjusted Stage 2 model.
stage2_results <- stage2_results |>
  mutate(
    nominally_significant_p_lt_0_05 =
      model_status == "ok" &
      !is.na(p_value) &
      p_value < 0.05
  )

stage2_significant_p_lt_0_05_n <- sum(
  stage2_results$nominally_significant_p_lt_0_05,
  na.rm = TRUE
)

stage2_results_with_summary <- summary_columns_for_results |>
  filter(exposure %in% stage2_exposures) |>
  left_join(stage2_results, by = "exposure") |>
  arrange(category, exposure)

# =============================================================================
# 8) Stage 1 volcano plots
# =============================================================================

stage1_plot_data <- bind_rows(stage1_training, stage1_testing) |>
  left_join(
    exposure_summary |>
      select(exposure, source, category),
    by = "exposure"
  ) |>
  mutate(split = factor(split, levels = c("Training", "Testing")))

combined_volcano <- make_volcano_plot(
  plot_dat = stage1_plot_data,
  facet = TRUE,
  x_lab = "Adjusted Odds Ratio",
  y_lab = "-log10(p-value)",
  focused_or_limits = NULL,
  focused_or_breaks = NULL
)
training_volcano <- make_volcano_plot(
  plot_dat = filter(stage1_plot_data, split == "Training"),
  facet = FALSE,
  x_lab = "Adjusted Odds Ratio (Training)",
  y_lab = "-log10(p-value) (Training)",
  focused_or_limits = NULL,
  focused_or_breaks = NULL
)
testing_volcano <- make_volcano_plot(
  plot_dat = filter(stage1_plot_data, split == "Testing"),
  facet = FALSE,
  x_lab = "Adjusted Odds Ratio (Testing)",
  y_lab = "-log10(p-value) (Testing)",
  focused_or_limits = NULL,
  focused_or_breaks = NULL
)

# Record every result outside the focused window. These rows remain in all
# statistical result tables and in the unconstrained volcano plots.
volcano_results_outside_focused_range <- stage1_plot_data |>
  filter(
    model_status == "ok",
    is.finite(OR),
    OR > 0,
    OR < volcano_focused_or_limits[1] |
      OR > volcano_focused_or_limits[2]
  ) |>
  arrange(split, OR) |>
  select(
    split,
    exposure,
    source,
    category,
    OR,
    CI_95_lower,
    CI_95_upper,
    p_value,
    p_bonferroni,
    bonferroni_significant,
    model_converged,
    model_status,
    model_error
  )

message(
  "Focused volcano OR window: ",
  paste(volcano_focused_or_limits, collapse = " to "),
  "; estimates outside window=",
  nrow(volcano_results_outside_focused_range),
  ". See the unconstrained volcano plots and supplemental QC table."
)

if (!is.null(combined_volcano)) {
  ggsave(
    filename = file.path(figures_dir, "stage1_volcano_training_testing_combined.png"),
    plot = combined_volcano,
    width = volcano_width,
    height = volcano_height,
    dpi = volcano_dpi
  )
  ggsave(
    filename = file.path(figures_dir, "stage1_volcano_training_testing_combined.pdf"),
    plot = combined_volcano,
    width = volcano_width,
    height = volcano_height
  )
}

if (!is.null(training_volcano)) {
  ggsave(
    filename = file.path(figures_dir, "stage1_volcano_training.png"),
    plot = training_volcano,
    width = volcano_width,
    height = volcano_height,
    dpi = volcano_dpi
  )
  ggsave(
    filename = file.path(figures_dir, "stage1_volcano_training.pdf"),
    plot = training_volcano,
    width = volcano_width,
    height = volcano_height
  )
}

if (!is.null(testing_volcano)) {
  ggsave(
    filename = file.path(figures_dir, "stage1_volcano_testing.png"),
    plot = testing_volcano,
    width = volcano_width,
    height = volcano_height,
    dpi = volcano_dpi
  )
  ggsave(
    filename = file.path(figures_dir, "stage1_volcano_testing.pdf"),
    plot = testing_volcano,
    width = volcano_width,
    height = volcano_height
  )
}

# =============================================================================
# 9) Save tables, RDS objects, and analysis-flow information
# =============================================================================

analysis_flow <- data.frame(
  step = c(
    "Manifest exposures",
    "Eligible after unique-value and missingness QC",
    "Excluded for high pairwise correlation",
    "Retained after correlation screening",
    "Excluded for insufficient split-specific variation",
    "Stage 1 exposures tested",
    "Bonferroni significant in training",
    "Bonferroni significant in testing",
    "Bonferroni significant in both",
    "Selected for Stage 2",
    "Stage 2 coefficients successfully estimated",
    "Stage 2 exposures with nominal p < 0.05"
  ),
  n = c(
    length(exposure_vars_manifest),
    length(eligible_after_unique_qc),
    length(correlation_pruning$excluded),
    length(correlation_pruning$retained),
    length(split_excluded_exposures),
    length(stage1_exposures),
    sum(stage1_training$bonferroni_significant, na.rm = TRUE),
    sum(stage1_testing$bonferroni_significant, na.rm = TRUE),
    sum(stage1_combined$significant_in_both_splits, na.rm = TRUE),
    length(stage2_exposures),
    sum(stage2_results$model_status == "ok", na.rm = TRUE),
    stage2_significant_p_lt_0_05_n
  ),
  stringsAsFactors = FALSE
)

# All requested workshop tables.
write.csv(
  exposure_qc,
  file.path(tables_dir, "01_exposure_unique_value_and_inclusion_qc.csv"),
  row.names = FALSE
)
write.csv(
  filter(exposure_qc, !is.na(final_exclusion_reason)),
  file.path(tables_dir, "02_excluded_exposures_and_reasons.csv"),
  row.names = FALSE
)
write.csv(
  scaling_parameters,
  file.path(tables_dir, "03_exposure_scaling_parameters.csv"),
  row.names = FALSE
)
write.csv(
  high_correlation_pairs,
  file.path(tables_dir, "04_high_correlation_pairs.csv"),
  row.names = FALSE
)
write.csv(
  correlation_decisions,
  file.path(tables_dir, "05_correlation_retained_excluded_decisions.csv"),
  row.names = FALSE
)
write.csv(
  exposure_summary,
  file.path(tables_dir, "06_exposure_summary_statistics_original_scale.csv"),
  row.names = FALSE
)
write.csv(
  stage1_training,
  file.path(tables_dir, "07_stage1_training_results.csv"),
  row.names = FALSE
)
write.csv(
  stage1_testing,
  file.path(tables_dir, "08_stage1_testing_results.csv"),
  row.names = FALSE
)
write.csv(
  stage1_results_with_summary,
  file.path(tables_dir, "09_stage1_training_testing_results_with_summary.csv"),
  row.names = FALSE
)
write.csv(
  stage1_selected_for_stage2,
  file.path(tables_dir, "10_stage1_exposures_selected_for_stage2.csv"),
  row.names = FALSE
)
write.csv(
  stage2_results_with_summary,
  file.path(tables_dir, "11_stage2_multiexposure_results_with_summary.csv"),
  row.names = FALSE
)
write.csv(
  split_summary,
  file.path(tables_dir, "12_training_testing_split_summary.csv"),
  row.names = FALSE
)
write.csv(
  analysis_flow,
  file.path(tables_dir, "13_exwas_analysis_flow_counts.csv"),
  row.names = FALSE
)
write.csv(
  volcano_results_outside_focused_range,
  file.path(tables_dir, "14_volcano_results_outside_focused_or_range.csv"),
  row.names = FALSE
)

# Preserve core analysis objects for later workshop exercises and troubleshooting.
preprocessing_objects <- list(
  settings = list(
    outcome_var = outcome_var,
    id_var = id_var,
    adjustment_covariates = adjustment_covariates,
    categorical_covariates = categorical_covariates,
    unique_value_fraction_threshold = unique_value_fraction_threshold,
    minimum_continuous_unique = minimum_continuous_unique,
    minimum_binary_cell_count = minimum_binary_cell_count,
    maximum_missing_fraction = maximum_missing_fraction,
    correlation_method = correlation_method,
    correlation_threshold = correlation_threshold,
    correlation_seed = correlation_seed,
    training_fraction = training_fraction,
    split_seed = split_seed,
    alpha = alpha,
    mice_m = mice_m,
    mice_maxit = mice_maxit,
    mice_seed = mice_seed,
    require_same_direction_for_stage2 = require_same_direction_for_stage2,
    volcano_focused_or_limits = volcano_focused_or_limits,
    volcano_focused_or_breaks = volcano_focused_or_breaks
  ),
  exposure_manifest = manifest,
  exposure_qc = exposure_qc,
  exposure_summary = exposure_summary,
  scaling_parameters = scaling_parameters,
  correlation_matrix = correlation_results$correlation_matrix,
  high_correlation_pairs = high_correlation_pairs,
  correlation_pruning = correlation_pruning,
  split_assignment = split_assignment,
  split_summary = split_summary,
  split_eligibility = split_eligibility,
  stage1_exposures = stage1_exposures,
  stage2_exposures = stage2_exposures,
  single_imputation_method = single_imputation$method,
  single_imputation_predictor_matrix = single_imputation$predictor_matrix,
  single_imputation_missing_cells_before = single_imputation$missing_cells,
  single_imputation_logged_events = single_imputation$logged_events
)

saveRDS(
  preprocessing_objects,
  file.path(rds_dir, "exwas_preprocessing_objects.rds")
)
saveRDS(
  single_imputed_output,
  file.path(rds_dir, "single_imputed_analysis_dataset.rds")
)
saveRDS(
  list(
    training = stage1_training,
    testing = stage1_testing,
    combined = stage1_combined,
    results_with_summary = stage1_results_with_summary,
    selected_for_stage2 = stage1_selected_for_stage2,
    volcano_results_outside_focused_range =
      volcano_results_outside_focused_range
  ),
  file.path(rds_dir, "stage1_exwas_results.rds")
)
saveRDS(
  list(
    selected_exposures = stage2_exposures,
    model_results = stage2_results,
    results_with_summary = stage2_results_with_summary
  ),
  file.path(rds_dir, "stage2_multiexposure_results.rds")
)

if (isTRUE(save_mids_object) && !is.null(single_imputation$mids)) {
  saveRDS(
    single_imputation$mids,
    file.path(rds_dir, "mids_single_full_sample.rds")
  )
}

capture.output(
  sessionInfo(),
  file = file.path(output_dir, "R_session_information.txt")
)

message("ExWAS workflow complete. Outputs saved under: ", output_dir)
print(split_summary)
print(analysis_flow)

# End of script.