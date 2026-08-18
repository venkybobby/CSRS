# Cost controls — what spends money in this project, and how to stop it

**Written 2026-08-16, after the project bill reached $256 and Vertex AI began
returning `Lightning dunning decision is deny`.**

Every command below reads `$PROJECT_ID` / `$PROJECT_NUMBER` / `$REGION` —
`source .env.ops` first (see `.env.ops.example` for the shape; real values
were moved out of `HEAD` as part of the pre-publish scrub, see "Before going
public" below for why that's hygiene rather than a credential concern).

Run the steps in order. Step 0 is not optional: while the dunning hold is in
place, every Vertex AI call fails — including the delete calls that stop the
spend.

---

## What is actually costing money

Measured, not guessed:

| Resource | State | Cost shape |
|---|---|---|
| **Reasoning Engines** | one per deploy since 2026-08-09, never deleted | **The bill.** Each is managed compute billed continuously |
| Cloud SQL `my-db-instance` | `db-f1-micro`, zonal, RUNNABLE | ~$9/month |
| Cloud Run × 2 | `minScale: 0` | Scales to zero; negligible |
| Artifact Registry | ~5 GB Docker | A few dollars |
| Cloud Build | ~10 min per PR/deploy | Cents per build |

Nothing except the engines is capable of producing $256. They were on the
open-items list as housekeeping — "25 orphan reasoning engines, nothing reaps
them." That was not housekeeping. It was a meter.

**Why they accumulate is deliberate, and the design is sound.** Per plan §6.2,
each deploy creates a *new* engine rather than mutating one in place: the BFF
pins a specific resource name, so rollback is a repoint rather than a
redeploy. That is a good property and worth keeping. The missing half is that
nothing ever deletes the superseded ones — so a rollback strategy quietly
became an accumulation strategy.

---

## Step 0 — clear the billing hold (a human, in the console)

`Lightning dunning decision is deny` is a payment-collections hold. Billing
shows `billingEnabled: True` and the account `OPEN`, and every other API
(Cloud Build, Cloud Run, Cloud SQL, Secret Manager) still works — the denial
is scoped to Vertex AI. Resolve the balance or payment instrument on billing
account `01C445-025BEF-66400F` ("SARO", shared with your other project).

Verify it has lifted before continuing — this must print `200`:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $(gcloud auth print-access-token)" "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT_NUMBER/locations/$REGION/reasoningEngines?pageSize=1"
```

---

## Step 1 — see what you are paying for

`gcloud beta ai reasoning-engines` needs the `beta` component, which will not
install without administrator rights on this machine. Use the REST API, which
needs nothing:

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT_NUMBER/locations/$REGION/reasoningEngines?pageSize=100" | python -c "import sys,json;[print(e['name'].split('/')[-1], e.get('createTime','')) for e in json.load(sys.stdin).get('reasoningEngines',[])]"
```

---

## Step 2 — delete every engine except the two newest

Keep two: the one the BFF currently serves, and one to roll back to. Delete
the rest. This is irreversible, and it is meant to be — a deploy rebuilds any
of them from source in about ten minutes.

**Check which one the BFF is actually pinned to first, and never delete it:**

```bash
gcloud run services describe $BFF_SERVICE --region=$REGION --project=$PROJECT_ID --format="value(spec.template.spec.containers[0].env)" | tr ',' '\n' | grep AGENT_ENGINE
```

Then delete all but the newest two:

```bash
TOKEN=$(gcloud auth print-access-token)
curl -s -H "Authorization: Bearer $TOKEN" "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT_NUMBER/locations/$REGION/reasoningEngines?pageSize=100" | python -c "import sys,json;e=json.load(sys.stdin).get('reasoningEngines',[]);e.sort(key=lambda x:x.get('createTime',''),reverse=True);[print(x['name']) for x in e[2:]]" > /tmp/engines-to-delete.txt
```

**Read `/tmp/engines-to-delete.txt` before running the next line.** Confirm the
BFF's engine is not in it.

```bash
while read -r name; do curl -s -X DELETE -H "Authorization: Bearer $TOKEN" "https://$REGION-aiplatform.googleapis.com/v1/${name}?force=true" -o /dev/null -w "deleted ${name##*/}: %{http_code}\n"; done < /tmp/engines-to-delete.txt
```

---

## Step 3 — stop the accumulation in CI

Without this, the next merge starts the meter again. Add a reaping step to
`cloudbuild/deploy.yaml`, after `deploy-bff` has successfully repointed at the
new engine — reaping earlier would delete the rollback target while the
rollback might still be needed.

```yaml
  - id: reap-old-agent-engines
    name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: bash
    args:
      - -c
      - >
        TOKEN=$$(gcloud auth print-access-token) &&
        curl -s -H "Authorization: Bearer $$TOKEN"
        "https://${_REGION}-aiplatform.googleapis.com/v1/projects/${_PROJECT_NUMBER}/locations/${_REGION}/reasoningEngines?pageSize=100"
        | python3 -c "import sys,json;e=json.load(sys.stdin).get('reasoningEngines',[]);e.sort(key=lambda x:x.get('createTime',''),reverse=True);[print(x['name']) for x in e[2:]]"
        | while read -r n; do curl -s -X DELETE -H "Authorization: Bearer $$TOKEN" "https://${_REGION}-aiplatform.googleapis.com/v1/$$n?force=true"; done
```

Keep the two-newest rule rather than one: the whole reason plan §6.2 creates a
new engine per deploy is so rollback is a repoint, and that needs a target to
repoint *to*.

---

## Step 4 — pause the database while dev is dormant

Only if you are not actively developing. Cloud SQL bills for a running
instance whether or not anything connects.

```bash
gcloud sql instances patch my-db-instance --project=$PROJECT_ID --activation-policy=NEVER
```

Restart with `--activation-policy=ALWAYS`. Storage still bills while stopped;
this saves the compute, roughly two thirds.

**Do not delete it.** It holds `quote_audit_log`, and Meridian's retention
decision is seven years from creation.

---

## Before going public — are the identifiers in this doc a real exposure?

**Checked 2026-08-18.** This doc used to name the project ID, the project
number, both Cloud Run service names, and several reasoning-engine resource
IDs directly -- now moved to `.env.ops` (see the top of this doc) as part of
the pre-publish scrub, closing the self-referential edge of a section about
exposure that itself contained the identifiers it was evaluating. Before
deciding whether making the repo public needs a git-history purge (an
afternoon vs. not worth doing), verified whether any of it is reachable
without authentication -- a bare project ID is not a secret in the
credential sense, so the real question is exposure, not presence.

**Cloud Run (both services):** IAM invoker policy grants `roles/run.invoker`
to exactly one member -- IAP's own service agent
(`service-<redacted>@gcp-sa-iap.iam.gserviceaccount.com`). No `allUsers`,
no `allAuthenticatedUsers`. Ingress is `internal-and-cloud-load-balancing`
on both -- the direct `*.run.app` URLs aren't routable from the public
internet at all, IAM aside. Confirmed empirically: an unauthenticated curl
to both direct URLs returns a bare 404 with no app content and no `server:
Google Frontend` header -- the request never reaches Cloud Run's own auth
check, let alone the container.

```bash
gcloud run services get-iam-policy $BFF_SERVICE --project=$PROJECT_ID --region=$REGION
# -> roles/run.invoker granted only to the IAP service agent

gcloud run services describe $BFF_SERVICE --project=$PROJECT_ID --region=$REGION \
  --format="value(metadata.annotations['run.googleapis.com/ingress'])"
# -> internal-and-cloud-load-balancing (both services)

curl -sI "$(gcloud run services describe $BFF_SERVICE --project=$PROJECT_ID --region=$REGION --format='value(status.url)')"
# -> HTTP/1.1 404 Not Found, no app content, no Google Frontend header
```

**Reasoning engines:** no bare URL exists for them at all -- access is
exclusively through `aiplatform.googleapis.com` with a mandatory
`Authorization: Bearer` token. Even a fully authenticated call from the
project owner's own account currently gets a 403 response quoting
`projects/<redacted>` back (the billing hold, step 0 above) -- an anonymous
caller has nothing to hit. Knowing a numeric resource ID grants no reach
without IAM permission on that specific resource.

**Conclusion: hygiene, not a requirement.** The project ID, service names,
and reasoning-engine IDs name things -- they don't open them. Step zero
(Wednesday) is scoped accordingly: move them out of `HEAD` (env vars or an
untracked ops file), re-run the sweep against the post-scrub state, then
flip public. An 81-commit history purge is not justified by actual exposure
and should not be done by default just because "sweep" is in the name --
this is what settles that before doing the more expensive thing.

**Gotcha carried over from today's sweep:** `git check-ignore` in this
environment fabricates a match for *any* path ending in `.claude/`,
including ones that don't exist (`git check-ignore -v
made/up/nonexistent.claude/` "matches"). Verify anything moved out of
tracking with `git status --ignored=matching` (look for `!!`), not
`check-ignore` -- that is how `infra/envs/.claude/` was found genuinely
unprotected today after an earlier pass wrongly called it covered.

---

## What none of this affects

Every client-facing artefact is generated from `db/seed` through the real
calculator and rendered by a local vite dev server — no agent, no BFF, no
database, no quota. See [`../demo/README.md`](../demo/README.md).

So the deck, the client summary, the 18 screenshots and the walkthrough video
can all be rebuilt, re-recorded and sent with **the entire GCP project turned
off**. The only thing that needs the cloud is a live demonstration against the
deployed agent, and that is deferred rather than blocked — the same evidence
is already recorded in the post-deploy eval runs, with build ids and dates.
