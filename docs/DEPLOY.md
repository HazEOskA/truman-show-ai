# Deploying Hydra to Cloud Run

Hydra is three processes and a database. Two of the processes are ordinary web services and
the third is not, and almost everything below follows from that difference.

```
observatory (Next.js)  ──►  api (FastAPI)  ──►  Cloud SQL (Postgres)
                                                     ▲
                              worker (the clock)  ───┘
```

---

## What Cloud Run changes about this stack

Four things, and each one needs a decision rather than a flag.

**The worker is not a web service.** It is a loop that owns time. Cloud Run keeps a container
alive only while it answers on `$PORT`, so the worker is deployed as `hydra_worker.service`,
which runs the same loop and puts a health endpoint beside it. The loop stays on the main
thread — `SimulationWorker.run_forever` installs signal handlers so a shutdown finishes the
tick in flight, and Python only allows that on the main thread.

**The worker must be a singleton.** It owns the clock for a timeline. Two instances advancing
the same timeline would interleave ticks and overwrite each other's state, and nothing would
report an error — the world would just stop being a consequence of its own rules. That is
`--max-instances=1`, and it is a correctness constraint, not a cost setting.

**The worker needs CPU when no request is in flight.** By default Cloud Run throttles a
container's CPU between requests. A throttled worker stops advancing the world and starts
again when someone happens to hit its health check, which looks exactly like a simulation
that has mysteriously slowed down. That is `--no-cpu-throttling` plus `--min-instances=1`.

**The filesystem is gone.** Cloud Run containers get ephemeral disk and can be replaced at
any moment, so the default `FileStore` would lose the world. `PostgresStore` is what runs in
the cloud; it is the same interface and the same tests.

One more, smaller: a City View stream is a long-lived SSE connection, and Cloud Run caps a
request at 60 minutes. The client already reconnects and always receives a fresh keyframe
first, so a cut connection costs a redraw and nothing else — but set `--timeout=3600` so it
happens hourly rather than every five minutes.

---

## What it actually costs to run

Measured on the real world, not estimated:

| | |
|---|---|
| Genesis, 48 000 residents | 4.6 s, 246 MB peak |
| One simulated day (144 ticks) | 5.2 s, 36 ms/tick |
| Live state written to the database | 2.8 MB gzipped |
| Projection served to a viewer | 40 kB gzipped, once |
| Delta per tick, per viewer | 0.4 kB gzipped |

So `--memory=1Gi` is comfortable for both Python services and 512Mi is the floor.

The one number worth watching is the live-state write. The worker republishes the whole world
every `HYDRA_LIVE_EVERY_TICKS` ticks, and at the default speed that is 2.8 MB every second or
two. On the smallest Cloud SQL tier that is noticeable. Raise `HYDRA_LIVE_EVERY_TICKS`, or run
the world slower, and it goes away — the trade is that City View motion gets coarser, since
the frame stream can only be as fine-grained as the publishing interval.

---

## Prerequisites

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com sqladmin.googleapis.com
```

---

## 1. A database

This is the one step that costs money continuously, so it is deliberate rather than
scripted. The smallest tier is enough for one city.

```bash
REGION=europe-central2

gcloud sql instances create hydra-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=$REGION \
  --storage-size=10GB

gcloud sql databases create hydra --instance=hydra-db
gcloud sql users set-password postgres --instance=hydra-db --password='CHANGE_ME'
```

Load the schema — it carries the append-only guard that makes a sealed timeline sealed:

```bash
gcloud sql connect hydra-db --user=postgres --database=hydra < database/schema.sql
```

The connection name (`PROJECT:REGION:hydra-db`) is what the services attach to:

```bash
gcloud sql instances describe hydra-db --format='value(connectionName)'
```

---

## 2. Keep the connection string out of the service config

Cloud Run environment variables are readable by anyone who can describe the service, so put
the whole connection string in Secret Manager and hand the services a reference instead:

```bash
SQL_INSTANCE=$(gcloud sql instances describe hydra-db --format='value(connectionName)')

printf 'postgresql://postgres:CHANGE_ME@/hydra?host=/cloudsql/%s' "$SQL_INSTANCE" \
  | gcloud secrets create hydra-dsn --data-file=-

# Cloud Run's runtime service account has to be allowed to read it.
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding hydra-dsn \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor
```

## 3. Build and deploy

```bash
python scripts/deploy_cloudrun.py \
  --project YOUR_PROJECT_ID \
  --region europe-central2 \
  --sql-instance YOUR_PROJECT_ID:europe-central2:hydra-db \
  --dsn-secret hydra-dsn
```

`--db-password 'CHANGE_ME'` works too and skips the secret, at the cost of storing the
password in plain sight. The script says so when you use it.

The script builds the three images, then deploys in the only order that works: the API
first, because the Observatory needs to be told its address; the Observatory second; the
worker last, with the singleton flags. It prints every `gcloud` command it runs, so it is
also a readable answer to "what would I type by hand".

`--dry-run` prints the commands without running any of them.

---

## 4. Create a world and start it

Genesis takes about five seconds and is a normal API call:

```bash
API=$(gcloud run services describe hydra-api --region=$REGION --format='value(status.url)')

# Read the world id back rather than assuming it: the API derives one from the seed, and a
# world created another way (scripts/run_world.py, for instance) will have a different one.
WORLD=$(curl -sX POST "$API/worlds" -H 'content-type: application/json' \
        -d '{"seed": 20260826, "name": "Hydra"}' \
        | python -c 'import json,sys; print(json.load(sys.stdin)["world_id"])')

curl -X POST "$API/worlds/$WORLD/timelines/tl_zero/control" \
     -H 'content-type: application/json' \
     -d '{"mode": "running", "speed": 2.0}'
```

Then open the Observatory's URL and go to **/city**.

---

## Doing it by hand

The script is only these commands. The flags that are not obvious are annotated.

```bash
# --set-secrets keeps the connection string in Secret Manager. To pass it directly instead,
# use --set-env-vars with the ^X^ form and an X that appears in none of the values: the
# default separator is a comma, which a password may contain, and the obvious alternative
# is @, which a DSN always contains.
SECRET=hydra-dsn:latest

# API — public, streams SSE, so it needs the long request timeout.
gcloud run deploy hydra-api \
  --image=$REGION-docker.pkg.dev/$PROJECT/hydra/api:latest \
  --region=$REGION --allow-unauthenticated \
  --memory=1Gi --cpu=1 --timeout=3600 \
  --add-cloudsql-instances=$SQL_INSTANCE \
  --set-secrets="HYDRA_DATABASE_URL=$SECRET" \
  --set-env-vars="HYDRA_CORS_ORIGINS=*"

API_URL=$(gcloud run services describe hydra-api --region=$REGION --format='value(status.url)')

# Observatory — reads the API address at request time, so the image is not tied to one API.
gcloud run deploy hydra-observatory \
  --image=$REGION-docker.pkg.dev/$PROJECT/hydra/observatory:latest \
  --region=$REGION --allow-unauthenticated \
  --memory=512Mi --cpu=1 \
  --set-env-vars="HYDRA_API_URL=$API_URL"

# Worker — exactly one, CPU always on, never reachable from outside.
# This is the process that consults Gemini: agent brains run inside the tick loop, so the
# model credentials belong here and nowhere else. The API and the Observatory never hold them.
gcloud run deploy hydra-worker \
  --image=$REGION-docker.pkg.dev/$PROJECT/hydra/worker:latest \
  --region=$REGION --no-allow-unauthenticated \
  --memory=1Gi --cpu=1 \
  --min-instances=1 --max-instances=1 --no-cpu-throttling \
  --add-cloudsql-instances=$SQL_INSTANCE \
  --set-secrets="HYDRA_DATABASE_URL=$SECRET,GEMINI_API_KEY=gemini-api-key:latest" \
  --set-env-vars="HYDRA_LIVE_EVERY_TICKS=6"
```

Tighten `HYDRA_CORS_ORIGINS` to the Observatory's URL once you know it.

## Letting the agents think

The world runs on rules with no provider configured, and that is the supported default. To
put Gemini behind the most important agents' decisions, the worker needs a credential and the
world needs its LLM section switched on.

Create the secret once, and let the worker's service account read it:

```bash
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:$WORKER_SA" --role=roles/secretmanager.secretAccessor
```

**Or no key at all.** The adapter uses Google's GenAI SDK, so on Cloud Run it can reach Gemini
through Vertex AI with the service account the container already has — nothing to mint, mount
or rotate:

```bash
gcloud run services update hydra-worker --region=$REGION \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION"
```

Either way the world's config has to enable it — `llm.enabled = true`, `llm.provider =
"gemini"` — and the models default to `gemini-3.5-flash`.

Two things worth being clear about before you demonstrate this:

* **A world with Gemini on does not replay to the same state hash.** The LLM section is
  excluded from `config_hash` on purpose, so the determinism tests stay green, but a model
  answers differently on different runs. Determinism and model-driven agents are two separate
  runs, and presenting them as one would be a claim this repository does not make.
* **The provider can never break the world.** Every failure — bad key, quota, timeout, a
  refusal — degrades that one agent to its rules for that one tick. The city keeps running.

---

## When something is wrong

**The city is frozen but nothing is failing.** The worker is throttled. Check that
`--no-cpu-throttling` and `--min-instances=1` are actually set — a redeploy without them
silently drops both.

**The Observatory loads but every panel is empty.** It is talking to the wrong API. View
source and look for `window.__HYDRA_API_URL__`; if it says `localhost`, `HYDRA_API_URL` was
not set on the Observatory service.

**Requests to the API fail with a database error after an idle period.** Cloud SQL drops idle
connections. The store reconnects when psycopg reports the connection broken, so this should
cost one request; if it persists, the DSN is wrong rather than the connection stale.

**Genesis times out.** It takes ~5 s for 48 000 residents but runs inside one request. If you
have raised the population a long way, raise `--timeout` on the API too.

**The world advances twice as fast as it should.** There are two workers. `--max-instances=1`.

---

## Is Cloud Run the right shape for this?

For one always-on city with one viewer, a small VM is simpler and cheaper: no singleton
flags, no CPU-throttling trap, no Cloud SQL socket. Cloud Run earns its keep when the
Observatory is the part that gets traffic — it scales the read side to zero when nobody is
watching, while the worker keeps the city running on one small always-on instance.
