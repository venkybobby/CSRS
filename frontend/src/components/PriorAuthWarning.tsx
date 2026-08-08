export function PriorAuthWarning({ cptCode, planName }: { cptCode: string; planName: string }) {
  return (
    <div className="banner banner-prior-auth" role="alert">
      <div className="banner-icon">⚠️</div>
      <div>
        <div className="banner-title">Prior Authorization Required</div>
        <p className="banner-message">
          Prior authorization is required for {cptCode} under {planName}. Advise the member to
          obtain authorization before service. The cost estimate below assumes auth is
          approved.
        </p>
      </div>
    </div>
  );
}
