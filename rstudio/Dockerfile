# RStudio Server for the ISEE 2026 workshop — a sibling of the app, not a
# replacement for it. Attendees link exposures in the web app (ports 3000/8000)
# and analyse the results in R here (port 8787).
#
# Why its own container rather than R inside the devcontainer: the codespace
# base image is Ubuntu 20.04 (focal), where this stack simply cannot be built —
# Posit serves no focal binaries for arrow/mice (source only), arrow >= 23
# needs C++20 which focal's gcc 9.4 cannot provide, and RStudio Server no
# longer publishes a focal .deb (404). rocker ships R and RStudio prebuilt on a
# supported base, for amd64 AND arm64, so this runs natively both in Codespaces
# (x86) and on an Apple Silicon laptop.
FROM rocker/rstudio:4.5.3

# System libraries the R packages link against. rocker configures the Posit
# package manager as the default repo, so install.packages() below pulls
# prebuilt binaries and does not need compilers — these are runtime deps only.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcurl4-openssl-dev \
        libssl-dev \
        libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

# Packages used by the three workshop scripts. arrow reads the legacy parquet
# inputs; mice drags the largest dependency tree (lme4, jomo, mitml, pan,
# ordinal, ...); glmnet + Matrix drive the elastic net.
RUN install2.r --error --skipinstalled --ncpus -1 \
        arrow \
        dplyr \
        purrr \
        ggplot2 \
        mice \
        glmnet \
        jsonlite \
    && rm -rf /tmp/downloaded_packages

# catboost is not on CRAN, P3M, or apt — it ships as a GitHub release tarball
# wrapping one prebuilt 257 MB libcatboostr.so. Pinned to a release URL because
# there is no repository to resolve "latest" against. --no-test-load skips
# dlopen at install time, which the wrapper does not need.
#
# The explicit stopifnot matters: install.packages() from a URL only WARNS on
# failure, so without it a missing dependency produced a green build and an
# image with no catboost — which would have surfaced mid-workshop, inside
# script 3. Fail here instead.
ARG CATBOOST_VERSION=1.2.10
RUN R -e "arch <- if (Sys.info()[['machine']] == 'aarch64') 'aarch64' else 'x86_64'; \
    url <- sprintf('https://github.com/catboost/catboost/releases/download/v%s/catboost-R-linux-%s-%s.tgz', \
                   '${CATBOOST_VERSION}', arch, '${CATBOOST_VERSION}'); \
    install.packages(url, repos = NULL, type = 'source', \
                     INSTALL_opts = c('--no-multiarch', '--no-test-load')); \
    stopifnot('catboost failed to install' = requireNamespace('catboost', quietly = TRUE))"

# Every package the three workshop scripts load must be importable in the
# shipped image — a build that silently loses one is worse than a build that
# fails, because the loss surfaces in front of an audience.
RUN R -e "pkgs <- c('arrow','dplyr','purrr','ggplot2','mice','glmnet','Matrix','jsonlite','catboost'); \
    missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly = TRUE)]; \
    if (length(missing)) stop('missing packages: ', paste(missing, collapse = ', ')); \
    cat('all workshop packages present\n')"

# The workshop scripts resolve everything under one project_dir; this is where
# docker-compose mounts ISSE26/, so the scripts need only that one path set.
ENV WORKSHOP_DIR=/home/rstudio/ISEE26Workshop
