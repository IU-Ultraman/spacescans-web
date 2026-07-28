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

> **Docker Desktop users (macOS/Windows):** give the Docker VM enough
> memory — **Settings → Resources → Memory ≥ 24 GB**. The pipeline reads
> multi-GB rasters inside the VM; at the ~8 GB default the run gets
> OOM-killed. Linux needs no setting — containers see all host RAM.

```bash
git clone https://github.com/IU-Ultraman/spacescans-web.git
cd spacescans-web
cp .env.docker.example .env      # then set SECRET_KEY — see step 1
docker compose up --build        # first build takes a few minutes
```

Then open `http://localhost:3000` and **sign up** to create an account.

The app runs without any exposure data — sign in and open **Data Setup**,
which lists every dataset, where to download it, and the exact folder to
drop it into under `pipeline-data/`. Add only the datasets for the
variables you plan to run.

---

## 1. Configure

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

## 2. Run

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
