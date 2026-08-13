// Story 4's AC specifies the warning as "[procedure name] under [plan name]"
// -- the friendly rate-sheet common_name and plans.display_name, not the raw
// CPT code and plan_id. The CPT is still shown, parenthesised, so the CSR can
// confirm which procedure was priced (Story 2).
export function PriorAuthWarning({
  procedureName,
  cptCode,
  planName,
}: {
  procedureName: string;
  cptCode: string;
  planName: string;
}) {
  return (
    <div className="banner banner-prior-auth" role="alert">
      <div className="banner-icon">⚠️</div>
      <div>
        <div className="banner-title">Prior Authorization Required</div>
        <p className="banner-message">
          Prior authorization is required for {procedureName} ({cptCode}) under {planName}.
          Advise the member to obtain authorization before service. The cost estimate below
          assumes auth is approved.
        </p>
      </div>
    </div>
  );
}
