# Client deliverables — what exists, who it is for, how to rebuild it

**CSRSupport MVP1 · Meridian Health Plans · current as of 2026-08-16**

Five artefacts go to the client, and they are generated from the same source
of truth rather than written alongside it. This page is the index: what each
one is for, what state it is in, and the order they must be rebuilt in.

The reason they are generated at all is that a hand-maintained deck cannot be
kept honest. The figures in every artefact below come from `db/seed` through
the real calculator, and the questions from `evals/demo_scripts.yaml` — so a
rate change or a calculator fix cannot leave a stale number on a slide without
also failing a test.

---

## The artefacts

| Artefact | Audience | Posture | State |
|---|---|---|---|
| [`../MVP1_STATUS.md`](../MVP1_STATUS.md) | Dana Whitfield | Read, referenced later | Current |
| [`steering-cut.html`](steering-cut.html) | Steering committee | **Presented** in a room | Current, 16 slides |
| [`client-summary.html`](client-summary.html) | Forwarded onward | **Read alone** | Current, 9 screens |
| `csrsupport-preview.webm` | Committee preview | Watched, ~108s, silent | Current, **not committed** |
| [`../CSR_WALKTHROUGH.md`](../CSR_WALKTHROUGH.md) | Carmen · Tyler · Marcus | Run sheet for the session | Current, 7 scenarios + 6b |

The deck and the summary deliberately share a palette — same people, same
system, same week — but not a posture. The deck opens with three asks and
exists to get a decision; the summary is read alone by someone who was not in
the room, so it leads with what was decided and holds each screenshot beside
the claim it supports.

`csrsupport-preview.webm` is gitignored (`.gitignore:50`). It is delivered out
of band, so **check its date before sending it** — nothing in CI will tell you
it has gone stale.

---

## Rebuild order — this is not optional

Each step reads the output of the one above it. Running them out of order
produces documents that disagree with each other and look authoritative doing
it.

```bash
# 0. Fixtures — the figures every downstream artefact quotes.
python scripts/generate_preview_fixtures.py

# 1. Screenshots — needs a vite dev server, nothing else.
npm --prefix frontend run dev          # in another shell
python scripts/capture_demo_screenshots.py

# 2. The two documents — both inline the PNGs as data URIs.
python scripts/build_demo_deck.py
python scripts/build_client_summary.py

# 3. The preview video — same dev server, no agent, no quota.
python scripts/record_demo_video.py --target preview
```

`pytest tests/unit/test_preview_fixtures.py` fails if step 0 was skipped.
Nothing catches a skipped step 1, which is why the order is written down: a
stale screenshot is worse than a missing one, because it reads as current.

Never hand-edit `previewPanes.json`, `docs/screenshots/`, `steering-cut.html`
or `client-summary.html`. Edit the generator; the deck's narration lives in
`SLIDES` in `scripts/build_demo_deck.py`.

---

## The capstone — what changed, and what still needs a person

The plan was a ten-minute narrated walkthrough recorded live against the
deployed agent. **That is deferred, and the fixture route now covers most of
what it was for.**

Two things moved:

- **The exchange is no longer live-only.** `VIDEO_PLAN.md` §3 recorded that a
  fixture could show the clarifying question but not the turn-taking, so only
  a live recording could demonstrate it. Turn 2 now exists as a fixture
  (`clarify-answered-knee`), resolved by the real `resolve_clarification`
  against the codes turn 1 offered. The one thing that made a live recording
  necessary is deterministic and free.
- **The dev agent is unreachable anyway.** Vertex AI on `csrs-504922` returns
  `Lightning dunning decision is deny` project-wide. See
  [`../architecture/cost-controls.md`](../architecture/cost-controls.md).

What a live recording would still add is honest latency and a real model in
the loop. That is worth having eventually; it is not worth a bill today, and
the same evidence exists in the post-deploy eval runs with build ids attached.

**The narration needs a person either way.** Playwright records the viewport
and no audio at all — no tooling changes that. The script is already written:
press <kbd>S</kbd> in `steering-cut.html` for the whole narration on one page,
including Demonstration 04, which walks the exchange.

---

## What these documents currently claim

Worth knowing before sending any of them, because they are deliberately
specific and a reviewer may check:

- 8/8 user stories · 109 unit · 17 integration · **20/20 offline** ·
  **22/22 live** · 15/15 rates diffed against Meridian's workbook · 4/4
  adversarial repelled · **0 CSRs have used it**
- The live number is observed, not forecast — build `4439a4d5`, engine
  `2985492378028081152`, the first deploy carrying the corrected seed. It
  becomes 24 on the next deployment, when the prior-auth pair joins it.
- The deck's "what we are not claiming" slide volunteers **nine** gaps,
  including the rate drift we found ourselves and the annual-physical question
  still open with Plan Ops.
