#!/usr/bin/env python3
"""Build and deploy Hydra to Cloud Run.

    python scripts/deploy_cloudrun.py --project my-project --region europe-central2 \
        --sql-instance my-project:europe-central2:hydra-db --db-password secret

Deploys in the only order that works: the API first, because the Observatory has to be told
its address; the Observatory second; the worker last, with the flags that make it a
singleton with CPU it can actually use.

Every command is printed before it runs, so this is also a readable answer to "what would I
type by hand". ``--dry-run`` prints them and runs nothing.

The database is deliberately *not* created here. It is the one part that costs money
continuously, and that decision should be made by a person reading ``docs/DEPLOY.md``, not
by a script someone ran to see what would happen.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

API_SERVICE = "hydra-api"
WEB_SERVICE = "hydra-observatory"
WORKER_SERVICE = "hydra-worker"


class Deployer:
    def __init__(self, gcloud: str, dry_run: bool) -> None:
        self.gcloud = gcloud
        self.dry_run = dry_run

    def run(self, *args: str, capture: bool = False) -> str:
        command = [self.gcloud, *args]
        print("\n$ " + " ".join(command), flush=True)
        if self.dry_run:
            return ""
        result = subprocess.run(
            command, cwd=ROOT, text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=None if capture else None,
        )
        if result.returncode != 0:
            raise SystemExit(f"\ngcloud failed with {result.returncode}")
        return (result.stdout or "").strip()


def image(region: str, project: str, repo: str, name: str, tag: str) -> str:
    return f"{region}-docker.pkg.dev/{project}/{repo}/{name}:{tag}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Hydra World to Cloud Run")
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", default="europe-central2")
    parser.add_argument("--repo", default="hydra", help="Artifact Registry repository")
    parser.add_argument("--tag", default="latest")
    parser.add_argument("--sql-instance", required=True,
                        help="Cloud SQL connection name, PROJECT:REGION:INSTANCE")
    parser.add_argument("--db-user", default="postgres")
    parser.add_argument("--db-password", help="password, passed as a plain environment variable")
    parser.add_argument("--dsn-secret",
                        help="Secret Manager secret holding the whole connection string; "
                             "preferred over --db-password, which is readable by anyone who "
                             "can describe the service")
    parser.add_argument("--db-name", default="hydra")
    parser.add_argument("--live-every-ticks", type=int, default=6,
                        help="how often the worker republishes the world; lower is smoother "
                             "motion and more database writes")
    parser.add_argument("--skip-build", action="store_true", help="reuse the images already pushed")
    parser.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
    args = parser.parse_args()

    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if gcloud is None:
        raise SystemExit("gcloud not found. Install the Google Cloud CLI and run `gcloud auth login`.")

    if not args.db_password and not args.dsn_secret:
        raise SystemExit("pass either --dsn-secret (preferred) or --db-password")
    if args.db_password:
        print("  note: --db-password stores the password in the service's environment, where\n"
              "        anyone who can describe the service can read it. --dsn-secret keeps it\n"
              "        in Secret Manager instead.")

    deployer = Deployer(gcloud, args.dry_run)
    region, project = args.region, args.project

    # The Cloud SQL socket, not a host and port: Cloud Run mounts the instance at
    # /cloudsql/<connection name> and psycopg takes that as the `host` parameter.
    dsn = (
        f"postgresql://{args.db_user}:{args.db_password}@/{args.db_name}"
        f"?host=/cloudsql/{args.sql_instance}"
        if args.db_password else ""
    )

    def database_flags(**extra: str) -> list[str]:
        """Every environment flag a Python service needs, in one place.

        Two things this has to get right. `gcloud` treats repeated `--set-env-vars` as
        *replacement*, not accumulation, so every variable has to go in a single flag or the
        last one silently wins and the database address disappears. And the delimiter cannot
        be assumed: the default is a comma, which a password may contain, and the obvious
        alternative is `@`, which a DSN *always* contains. So it is chosen against the actual
        values rather than picked in advance.

        A secret is a reference; a plain variable is the password itself, readable by anyone
        who can describe the service. Both are supported because the second is what people
        reach for on a first deploy, but the first is the one to keep.
        """

        flags: list[str] = []
        variables = dict(extra)
        if args.dsn_secret:
            flags.append(f"--set-secrets=HYDRA_DATABASE_URL={args.dsn_secret}:latest")
        else:
            variables["HYDRA_DATABASE_URL"] = dsn
        if variables:
            delimiter = _delimiter_for(variables)
            joined = delimiter.join(f"{key}={value}" for key, value in variables.items())
            flags.append(f"--set-env-vars=^{delimiter}^{joined}")
        return flags

    # Free and idempotent; creating it here saves one confusing failure on a first deploy.
    print("\n--- Artifact Registry ---")
    if _repo_exists(deployer, args.repo, project, region):
        print("  repository already exists")
    else:
        deployer.run(
            "artifacts", "repositories", "create", args.repo,
            "--repository-format=docker", f"--location={region}",
            "--description=Hydra World images",
            f"--project={project}",
        )

    if not args.skip_build:
        print("\n--- Build ---")
        deployer.run(
            "builds", "submit", "--config=cloudbuild.yaml",
            f"--substitutions=_REGION={region},_REPO={args.repo},_TAG={args.tag}",
            f"--project={project}",
        )

    print("\n--- API ---")
    deployer.run(
        "run", "deploy", API_SERVICE,
        f"--image={image(region, project, args.repo, 'api', args.tag)}",
        f"--region={region}", f"--project={project}",
        "--allow-unauthenticated",
        "--memory=1Gi", "--cpu=1",
        # SSE lives inside one request; Cloud Run's cap is 60 minutes and the default is 5.
        "--timeout=3600",
        f"--add-cloudsql-instances={args.sql_instance}",
        *database_flags(HYDRA_CORS_ORIGINS="*"),
    )

    api_url = deployer.run(
        "run", "services", "describe", API_SERVICE,
        f"--region={region}", f"--project={project}",
        "--format=value(status.url)", capture=True,
    ) or "https://API_URL_UNKNOWN"
    print(f"\n  API: {api_url}")

    print("\n--- Observatory ---")
    deployer.run(
        "run", "deploy", WEB_SERVICE,
        f"--image={image(region, project, args.repo, 'observatory', args.tag)}",
        f"--region={region}", f"--project={project}",
        "--allow-unauthenticated",
        "--memory=512Mi", "--cpu=1",
        # Read per request in app/layout.tsx, so the image is not welded to one API.
        f"--set-env-vars=HYDRA_API_URL={api_url}",
    )

    print("\n--- Worker ---")
    deployer.run(
        "run", "deploy", WORKER_SERVICE,
        f"--image={image(region, project, args.repo, 'worker', args.tag)}",
        f"--region={region}", f"--project={project}",
        # Nothing outside needs to reach the worker; only Cloud Run's own health checks do.
        "--no-allow-unauthenticated",
        "--memory=1Gi", "--cpu=1",
        # Exactly one, always warm, and with CPU between requests -- a throttled worker
        # stops advancing the world and looks like a simulation that has simply stalled.
        "--min-instances=1", "--max-instances=1", "--no-cpu-throttling",
        f"--add-cloudsql-instances={args.sql_instance}",
        *database_flags(HYDRA_LIVE_EVERY_TICKS=str(args.live_every_ticks)),
    )

    web_url = deployer.run(
        "run", "services", "describe", WEB_SERVICE,
        f"--region={region}", f"--project={project}",
        "--format=value(status.url)", capture=True,
    )

    print("\n" + "-" * 60)
    print(f"  Observatory  {web_url or '(unknown)'}")
    print(f"  City View    {web_url}/city" if web_url else "  City View    (unknown)")
    print(f"  API docs     {api_url}/docs")
    print("-" * 60)
    print("\nNo world exists yet. Create one and start the clock:\n")
    print(f'  curl -X POST "{api_url}/worlds" -H "content-type: application/json" \\')
    print('       -d \'{"seed": 20260826, "name": "Hydra"}\'')
    print(f'  curl -X POST "{api_url}/worlds/world_20260826/timelines/tl_zero/control" \\')
    print('       -H "content-type: application/json" -d \'{"mode": "running", "speed": 2.0}\'')
    print("\nThen tighten CORS to the Observatory's own URL.")
    return 0


def _delimiter_for(variables: dict[str, str]) -> str:
    """A separator that appears in none of the values.

    gcloud's ^X^ syntax swaps the comma for X, but X has to be a character the values do not
    contain -- otherwise the split lands in the middle of a password or a connection string
    and the service comes up with variables that are almost, but not quite, right.
    """

    blob = "".join(variables.keys()) + "".join(variables.values())
    for candidate in "|#%;!+~^":
        if candidate not in blob:
            return candidate
    raise SystemExit(
        "could not find a safe separator for the environment variables; "
        "use --dsn-secret instead of --db-password"
    )


def _repo_exists(deployer: Deployer, repo: str, project: str, region: str) -> bool:
    if deployer.dry_run:
        return False
    probe = subprocess.run(
        [deployer.gcloud, "artifacts", "repositories", "describe", repo,
         f"--location={region}", f"--project={project}", "--format=value(name)"],
        capture_output=True, text=True,
    )
    return probe.returncode == 0


if __name__ == "__main__":
    sys.exit(main())
