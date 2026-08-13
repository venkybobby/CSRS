import type { StandardCostResult } from "../types";
import { PriorAuthWarning } from "./PriorAuthWarning";

function money(value: string): string {
  const n = Number(value);
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function CostBreakdownTable({ result }: { result: StandardCostResult }) {
  const b = result.breakdown;
  // With a date of service, eligibility.warning holds a CONFIRMATION that the
  // date falls inside the coverage period -- the tool has already done the
  // checking the old warning asked the CSR to do. Rendering that under a ⚠️
  // would tell the CSR to worry about the exact thing that was just resolved.
  const dated = result.date_of_service !== null;
  return (
    <div className="cost-panel">
      {result.eligibility.warning && (
        <div
          className={dated ? "banner banner-confirm" : "banner banner-future-term"}
          role={dated ? "status" : "alert"}
        >
          <div className="banner-icon">{dated ? "✅" : "⚠️"}</div>
          <p className="banner-message">{result.eligibility.warning}</p>
        </div>
      )}

      {dated && (
        <div className="dos-line">
          <span className="dos-label">Date of service</span>
          <span className="dos-value">{result.date_of_service}</span>
        </div>
      )}

      {b.prior_auth_required && (
        <PriorAuthWarning
          procedureName={result.procedure.common_name ?? result.procedure.cpt_code ?? ""}
          cptCode={result.procedure.cpt_code ?? ""}
          planName={result.plan_display_name}
        />
      )}

      <table className="breakdown-table">
        <tbody>
          <tr>
            <th>Negotiated rate</th>
            <td>{money(b.negotiated_rate)}</td>
          </tr>
          <tr>
            <th>Deductible ({money(b.deductible_met_ytd)} met of {money(b.deductible_individual)})</th>
            <td>{money(b.deductible_remaining)} remaining</td>
          </tr>
          <tr>
            <th>Applied to deductible</th>
            <td>{money(b.applied_to_deductible)}</td>
          </tr>
          <tr>
            <th>Balance after deductible</th>
            <td>{money(b.balance_after_deductible)}</td>
          </tr>
          <tr>
            <th>Coinsurance ({(Number(b.coinsurance_pct) * 100).toFixed(0)}%)</th>
            <td>{money(b.coinsurance_amount)}</td>
          </tr>
          {b.oop_cap_triggered && (
            <tr className="row-highlight">
              <th>Out-of-pocket maximum reached</th>
              <td>capped at {money(b.oop_remaining)}</td>
            </tr>
          )}
          {result.eligibility.tier === "FAMILY" && b.triggering_threshold !== "N/A" && (
            <tr>
              <th>Deductible phase skipped via</th>
              <td>{b.triggering_threshold === "INDIVIDUAL" ? "individual" : "family"} threshold</td>
            </tr>
          )}
          <tr className="row-total">
            <th>Member owes</th>
            <td>{money(b.member_cost)}</td>
          </tr>
        </tbody>
      </table>

      {dated && (
        // The stated assumption behind every future-dated quote: eligibility
        // is exact as of the date of service, the dollars are not. Rendered
        // as its own line rather than buried in prose so it survives onto
        // anything the CSR later reads out or sends.
        <p className="estimate-assumption">
          Balances are as of today and may change before {result.date_of_service}.
        </p>
      )}

      <p className="audit-ref">Audit ref: {result.audit_id}</p>
    </div>
  );
}
