"""Build the client-facing MVP1 summary from the committed screenshots.

    python scripts/capture_demo_screenshots.py    # refresh the PNGs first
    python scripts/build_client_summary.py        # then rebuild this

Writes docs/demo/client-summary.html -- self-contained, every image inlined
as a data URI, so it opens from a file path, an email attachment or a hosted
page with no server and no external requests.

Distinct from steering-cut.html, and the difference is the audience's posture
rather than the content. The deck is presented: it opens with three asks and
exists to get a decision in a room. This is read, alone, probably forwarded
onward -- so it leads with what was decided and what came of it, and it holds
the screenshots inline where the claim they support is made.

Same palette and typography as the deck on purpose. These go to the same
people about the same system within the same week; looking like two unrelated
documents would be a small, avoidable tax on their attention.

Nothing here claims anything the repository cannot support. Every figure is a
test count, an eval result or a decision with a date against it.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHOTS_DIR = REPO_ROOT / "docs" / "screenshots"
OUTPUT = REPO_ROOT / "docs" / "demo" / "client-summary.html"

SCOREBOARD = [
    ("User stories implemented", "8 / 8", "Audited against your requirements document"),
    ("Unit tests", "109 passed", "Pure logic, no external services"),
    ("Integration tests", "17 passed", "Against a real PostgreSQL database"),
    ("Scenario suite, offline", "20 / 20", "Every figure pinned to your worked examples"),
    (
        "Rates vs. your workbook",
        "15 / 15",
        "Every negotiated rate diffed against rate_sheet_2026.xlsx on every build",
    ),
    ("Scenario suite, live", "22 / 22", "Run automatically on every deployment"),
    ("Adversarial attempts", "4 / 4 repelled", "Including a claimed supervisor override"),
]

DECISIONS = [
    (
        "One hour with two reps",
        "Scheduled",
        "Carmen and Tyler, with Marcus attending. A written run sheet covers seven "
        "scenarios; three of them are refusals, because that is what decides whether "
        "your reps trust it.",
    ),
    (
        "Promotion beyond development",
        "Approved for staging",
        "Contingent on the audit-log partition job we named ourselves. It is small and "
        "known, and it is the one genuine engineering prerequisite.",
    ),
    (
        "Rate-sheet update cadence",
        "Owned",
        "J. Morrow in Finance, monthly on the first business day, from September. This "
        "was the last item marked blocking production on your own requirements document.",
    ),
]

# (screenshot, eyebrow, heading, body)
SHOTS = [
    (
        "demo-1-partial-deductible.png",
        "An ordinary quote",
        "Every figure is shown, and every quote can be traced back.",
        "Deductible applied, balance, coinsurance rate, and the amount the member owes. "
        "The reference at the bottom resolves to the exact plan, rate and accumulator "
        "values that produced the number — independently of anything the language model "
        "said. If a figure ever has to be defended, you are defending a database row "
        "rather than a conversation.",
    ),
    (
        "demo-2-oop-cap.png",
        "Where a rep gets it wrong unaided",
        "The arithmetic a person does in their head is wrong here.",
        "Coinsurance on this surgery works out to $1,860. The member has $150 of "
        "out-of-pocket room left for the year, so $150 is what they owe. A rep working "
        "this manually reads the larger number aloud. The system caps it and shows why.",
    ),
    (
        "clarify-ambiguous-mri.png",
        "Your committee's question, answered — turn 1",
        "Asked for “an MRI”, it asks which one rather than choosing.",
        "This screen exists because of the question raised in your steering meeting: the "
        "model does not produce numbers, but it does pick the procedure — so what happens "
        "when it picks wrong? Testing that rather than answering it from the design found "
        "two real defects, both now fixed and both covered by the automated checks. Note "
        "there is no price on this screen at all: nothing is priced until the rep says which "
        "procedure they meant.",
    ),
    (
        "clarify-answered-knee.png",
        "…and turn 2",
        "The rep answers, and it prices what they said — named, with its code.",
        "The exchange completing. The rep answers “knee” and the system prices MRI Knee, "
        "CPT 73721. Every quote now names the procedure it priced, which is the honest answer "
        "to the one risk the design cannot remove: if the procedure were ever wrong, it would "
        "be wrong in the open, on the screen, in front of the person who can catch it. Worth "
        "saying plainly — that was not true a week ago. The ordinary cost screen showed a "
        "total without naming what it had priced, and we found it while building this pair.",
    ),
    (
        "demo-4-termed-block.png",
        "Refusal — coverage ended",
        "It does not quote with a warning attached. It does not quote.",
        "The member terminated on 31 May. Nothing about the procedure was looked up at "
        "all — the moment eligibility came back terminated, this stopped being a pricing "
        "question. A warning beside a price still leaves a price on the screen to read "
        "out under pressure.",
    ),
    (
        "dated-no.png",
        "Refusal — date of service",
        "Same member, same procedure, one date apart.",
        "Asked on the same day about the same knee MRI. A date inside the coverage period "
        "quotes normally; a date after coverage ends refuses and tells the rep not to "
        "quote. Everything is held constant except one variable, and the answer flips "
        "from a price to a refusal — which is how you can tell it is reasoning about the "
        "date rather than recognising the shape of the question.",
    ),
    (
        "exclusion-bronze.png",
        "Refusal — not a covered benefit",
        "“Not covered” and “no rate on file” are different regulatory facts.",
        "The same procedure code on two plans. On Bronze it is excluded, which triggers a "
        "member rights disclosure. On Silver it is simply not on the rate sheet — an "
        "operational gap and a different conversation. Your requirements are explicit "
        "that the wrong script for either is a grievance risk, so these are different "
        "types inside the system and cannot render as the same screen even by accident.",
    ),
    (
        "rate-not-found-silver.png",
        "The same code, the other plan",
        "Visibly different, by construction.",
        "The counterpart to the screen above: same procedure code, different plan, "
        "different label, different colour, different instruction to the rep.",
    ),
    (
        "demo-5-honest-miss.png",
        "Refusal — no rate on file",
        "Where it cannot stand behind a number, it says so.",
        "The procedure is not on the rate sheet. The system never interpolates, averages, "
        "or substitutes a nearby procedure's rate. It says what it does not have and "
        "hands the call to a person.",
    ),
]

NOT_CLAIMING = [
    "A confident wrong match is still possible. If the caller says knee and means brain, "
    "the system prices the knee, correctly. Nothing removes that — what it does is name "
    "the procedure on screen, so your rep confirms a stated thing rather than an "
    "unlabelled number.",
    "No rep has used the deployed interface. Everything here is verified by test; the "
    "seat in front of it has not been walked by a person. The hour with Carmen and Tyler "
    "closes this.",
    "The guardrail has not been watched firing in the real interface, nor its alert "
    "confirmed in monitoring.",
    "Only the development environment exists. Staging is approved but not built.",
    "Our seeded rates had drifted from your rate sheet — eight of them wrong, four of "
    "your procedures missing, three in our system you have never negotiated. Every "
    "figure ever shown to you was still correct, and not by luck: the only rates that "
    "were right were the ones derived from the worked examples in your own requirements "
    "document. It is corrected, and the build now fails on any disagreement with your "
    "workbook. The reason it happened is the part worth your attention — our check asks "
    "whether a number came from our data, and cannot ask whether our data was right. "
    "Only reading your workbook answers that, and now something does, on every build.",
    "Retention is recorded at seven years. The job that performs the deletion is not "
    "built — it belongs to the production promotion, and nothing is near the boundary.",
    "This supports a compliance position. It does not certify one. A person signs off, "
    "always.",
]

STYLE = """
:root {
  --ground: #F4F6F9; --surface: #FFFFFF;
  --ink: #0F161D; --ink-soft: #4C5A69; --ink-faint: #7A8794;
  --rule: #D9E1E9; --accent: #17456E;
  --ok: #1D5E4A; --refuse: #A81F17; --warn: #855400;
  --shadow: 0 1px 2px rgba(15,22,29,.05), 0 14px 34px rgba(15,22,29,.09);
  --serif: Georgia, "Iowan Old Style", "Times New Roman", serif;
  --sans: system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --mono: ui-monospace, "Cascadia Mono", Consolas, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #0C1117; --surface: #141B23;
    --ink: #E8EDF3; --ink-soft: #A7B3C1; --ink-faint: #77838F;
    --rule: #253039; --accent: #78ADDC;
    --ok: #5FBFA0; --refuse: #EF8B7F; --warn: #DFA83E;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 14px 34px rgba(0,0,0,.5);
  }
}
:root[data-theme="dark"] {
  --ground: #0C1117; --surface: #141B23;
  --ink: #E8EDF3; --ink-soft: #A7B3C1; --ink-faint: #77838F;
  --rule: #253039; --accent: #78ADDC;
  --ok: #5FBFA0; --refuse: #EF8B7F; --warn: #DFA83E;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 14px 34px rgba(0,0,0,.5);
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--ground); color: var(--ink);
  font-family: var(--sans); font-size: 17px; line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
main { max-width: 860px; margin: 0 auto; padding: clamp(32px,6vw,72px) clamp(20px,5vw,40px) 96px; }

.eyebrow {
  font-size: 12px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase;
  color: var(--accent); margin: 0 0 10px;
}
h1 {
  font-family: var(--serif); font-weight: 400; font-size: clamp(30px,4.4vw,46px);
  line-height: 1.14; letter-spacing: -.014em; text-wrap: balance; margin: 0 0 16px;
}
h2 {
  font-family: var(--serif); font-weight: 400; font-size: clamp(23px,2.7vw,30px);
  line-height: 1.2; margin: 0 0 12px; text-wrap: balance;
}
h3 { font-family: var(--serif); font-weight: 400; font-size: 21px; margin: 0 0 8px; }
p { margin: 0 0 16px; color: var(--ink-soft); text-wrap: pretty; }
p.lede { font-size: clamp(18px,1.7vw,21px); color: var(--ink-soft); }
strong { color: var(--ink); font-weight: 600; }
section { margin-top: 52px; }
hr { border: 0; border-top: 1px solid var(--rule); margin: 52px 0 0; }

.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 11px 16px 11px 0; border-bottom: 1px solid var(--rule); }
th {
  font-size: 11px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: var(--ink-faint);
}
td { font-size: 16px; color: var(--ink-soft); vertical-align: baseline; }
td.metric { color: var(--ink); font-weight: 600; }
td.value {
  font-family: var(--mono); font-variant-numeric: tabular-nums;
  color: var(--ok); white-space: nowrap; font-weight: 600;
}

.pill {
  display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase; padding: 3px 9px; border-radius: 999px;
  border: 1px solid currentColor; color: var(--ok); white-space: nowrap;
}

figure {
  margin: 0 0 40px; padding: 0;
  border-top: 1px solid var(--rule); padding-top: 28px;
}
figure img {
  display: block; width: 100%; height: auto; margin: 18px 0 0;
  border: 1px solid var(--rule); border-radius: 7px;
  background: var(--surface); box-shadow: var(--shadow);
}
figure .eyebrow { color: var(--refuse); }
figure[data-kind="quote"] .eyebrow { color: var(--accent); }
figure[data-kind="ask"] .eyebrow { color: var(--warn); }

ul.plain { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
ul.plain li {
  display: grid; grid-template-columns: 7px 1fr; gap: 15px;
  align-items: baseline; color: var(--ink-soft);
}
ul.plain li::before {
  content: ""; width: 6px; height: 6px; border-radius: 50%;
  background: var(--warn); transform: translateY(-2px);
}

.callout {
  border-left: 3px solid var(--accent); background: var(--surface);
  border-radius: 0 7px 7px 0; padding: 20px 24px; box-shadow: var(--shadow);
}
.callout p:last-child { margin-bottom: 0; }

footer {
  margin-top: 56px; padding-top: 22px; border-top: 1px solid var(--rule);
  color: var(--ink-faint); font-size: 14px;
}
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
"""


def esc(t: str) -> str:
    return html.escape(t, quote=False)


def data_uri(name: str) -> str:
    path = SHOTS_DIR / name
    if not path.exists():
        raise SystemExit(
            f"missing screenshot: {path}\nRun scripts/capture_demo_screenshots.py first."
        )
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _kind(eyebrow: str) -> str:
    if eyebrow.startswith("Refusal"):
        return "refusal"
    if "question" in eyebrow:
        return "ask"
    return "quote"


def build() -> str:
    scoreboard = "".join(
        f'<tr><td class="metric">{esc(m)}</td><td class="value">{esc(v)}</td>'
        f"<td>{esc(n)}</td></tr>"
        for m, v, n in SCOREBOARD
    )
    decisions = "".join(
        f'<tr><td class="metric">{esc(d)}</td>'
        f'<td><span class="pill">{esc(s)}</span></td><td>{esc(b)}</td></tr>'
        for d, s, b in DECISIONS
    )
    shots = "".join(
        f'<figure data-kind="{_kind(eyebrow)}">'
        f'<p class="eyebrow">{esc(eyebrow)}</p>'
        f"<h3>{esc(head)}</h3><p>{esc(body)}</p>"
        f'<img src="{data_uri(png)}" alt="{esc(head)}">'
        "</figure>"
        for png, eyebrow, head, body in SHOTS
    )
    not_claiming = "".join(f"<li>{esc(x)}</li>" for x in NOT_CLAIMING)

    return f"""<meta charset="utf-8">
<title>CSRSupport MVP1 Summary</title>
<style>{STYLE}</style>
<main>
  <p class="eyebrow">Meridian Health Plans · CSR Cost Estimator · 16 August 2026</p>
  <h1>MVP1 is built, verified, and waiting on an hour with two of your reps.</h1>
  <p class="lede">All three decisions from the steering review have landed. This is what
  the system does, what your committee's question turned up, and what we are not
  claiming.</p>

  <section>
    <h2>The three decisions, and what came of them</h2>
    <div class="tablewrap"><table>
      <thead><tr><th>Decision</th><th>Status</th><th>Where it stands</th></tr></thead>
      <tbody>{decisions}</tbody>
    </table></div>
  </section>

  <section>
    <h2>Where it stands</h2>
    <div class="tablewrap"><table>
      <thead><tr><th>Measure</th><th>Result</th><th>What it means</th></tr></thead>
      <tbody>{scoreboard}</tbody>
    </table></div>
    <p style="margin-top:18px">The live figure is the one worth weighing. It is not
    produced by someone running a script and reporting the result — it runs automatically
    on every deployment, against the build just shipped, and the deployment fails if it
    fails. It also checks that no member was priced before that member's own eligibility
    was checked, which is the guarantee no offline test can establish.</p>
    <div class="callout"><p><strong>Reps who have used the deployed interface: zero.</strong>
    That is the honest number in this document, and it is the one the hour with Carmen and
    Tyler exists to change.</p></div>
  </section>

  <section>
    <h2>What your committee's question found</h2>
    <p>The question was: the model does not produce numbers, but it does pick the
    procedure — so what happens when it picks the wrong one? We tested it rather than
    answering from the design, and it found two real defects.</p>
    <p>Asked for just <strong>“MRI”</strong>, the system chose one of three silently.
    Asked for an MRI inside an ordinary sentence, it wrongly reported that no rate was on
    file — which is not a hedge but a false statement about the rate sheet. <strong>Both
    are fixed, and both are now covered by the automated checks</strong> so they cannot
    return quietly.</p>
    <p>The honest boundary, stated plainly: the model can at worst aim the calculator at
    the wrong procedure. It can never invent what the calculator returns.</p>
  </section>

  <section>
    <h2>What a rep sees</h2>
    <p>Every screen below is captured from the running system, not mocked up. The figures
    come from the real calculator over the sample data, and each is stamped with the
    automated test case that pins it.</p>
    {shots}
  </section>

  <section>
    <h2>What we are not claiming</h2>
    <p>Stated before you ask, because a list like this is worth more from us than from
    your auditors.</p>
    <ul class="plain">{not_claiming}</ul>
  </section>

  <section>
    <h2>Next</h2>
    <p>The hour with Carmen and Tyler is the acceptance test, not a demo. Seven scenarios
    in a deliberate order, three of them refusals. Two things need arranging a day ahead:
    both reps in the access group, and someone with read access to the development
    database in the room — tracing a quote back to its audit record cannot be done from
    the rep's own screen, by design.</p>
    <p>What we will be listening for is not whether the numbers are right. It is every
    refusal a rep did not find convincing, and every number a rep accepted without
    checking. A refusal that is correct but reads as the tool being broken is a real
    defect.</p>
  </section>

  <footer>Prepared for Dana Whitfield · CSR-internal tool, not member-facing ·
  Figures verified 16 August 2026</footer>
</main>
"""


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build(), encoding="utf-8")
    kb = OUTPUT.stat().st_size / 1024
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT).as_posix()} ({kb:,.0f} KB, {len(SHOTS)} screens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
