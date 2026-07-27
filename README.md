# spacescans-web

Web app for the SPACESCANS EHR ↔ environmental-exposure linkage pipeline:
upload a patient cohort CSV, pick exposure variables, run the pipeline, and
explore the results.

The same setup runs on macOS, Windows, and Linux — everything runs inside
Docker containers, so there is nothing OS-specific to configure.

---

## Quick start

The only thing you install yourself is **Docker** (Docker Desktop on
macOS/Windows, Docker Engine on Linux).

```bash
git clone https://github.com/IU-Ultraman/spacescans-web.git
cd spacescans-web
cp .env.docker.example .env      # then set SECRET_KEY — see step 2
docker compose up --build        # first build takes a few minutes
```

Before the first run, put the exposure datasets (several GB) in
`pipeline-data/` — see step 1. Then open `http://localhost:3000` and
**sign up** to create an account.

---

## 1. Data

Put the exposure datasets (several GB, one folder per dataset — `BG/`,
`Noise/`, `TIGER/`, …) directly in **`pipeline-data/`** — see
[pipeline-data/README.md](pipeline-data/README.md) for the exact layout
and per-dataset sources. Already have the data elsewhere? Skip copying and set
`SPACESCANS_DATA_HOST=/abs/path` in `.env`.

---

## 2. Configure

```bash
cp .env.docker.example .env
```

Then set `SECRET_KEY` in `.env` to a random value. Generate one with:

```bash
openssl rand -hex 32
```

Open `.env` and replace the placeholder with the generated value:

```text
SECRET_KEY=<paste the generated value here>
```

Skipping this is fine for local testing — defaults apply — but set a real
secret for anything else.

---

## 3. Run

```bash
docker compose up --build
```

- **Frontend** → `http://localhost:3000`
- **Backend** → `http://localhost:8000`

The first build downloads ~1.5 GB of dependencies and takes a few minutes;
later runs are cached and fast. Open the frontend and **sign up** to create
an account.

```bash
docker compose down              # stop
docker compose down -v           # stop + also delete accounts/tasks/cache
docker compose logs -f backend   # follow backend logs
```
