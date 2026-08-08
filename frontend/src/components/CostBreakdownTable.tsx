import type { StandardCostResult } from "../types";
import { PriorAuthWarning } from "./PriorAuthWarning";

function money(value: string): string {
  const n = Number(value);
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function CostBreakdownTable({ result }: { result: StandardCostResult }) {
  const b = result.breakdown;
  return (
    <div className="cost-panel">
      {result.eligibility.warning && (
        <div className="banner banner-future-term" role="alert">
          <div className="banner-icon">⚠️</div>
          <p className="banner-message">{result.eligibility.warning}</p>
        </div>
      )}

      {b.prior_auth_required && (
        // plan_id (e.g. "MER-SLV-2026"), not a friendly display name --
        // StandardCostResult doesn't carry plans.display_name today. Good
        // enough for MVP1; a follow-up could add it to the API response.
        <PriorAuthWarning cptCode={result.procedure.cpt_code ?? ""} planName={result.eligibility.plan_id ?? ""} />
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

      <p className="audit-ref">Audit ref: {result.audit_id}</p>
    </div>
  );
}
