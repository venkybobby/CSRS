import type { CostEstimateResult } from "../types";
import { ClarificationPrompt } from "./ClarificationPrompt";
import { CostBreakdownTable } from "./CostBreakdownTable";
import { ExclusionBanner } from "./ExclusionBanner";
import { MemberNotFoundBanner } from "./MemberNotFoundBanner";
import { PreventiveBanner } from "./PreventiveBanner";
import { RateNotFoundBanner } from "./RateNotFoundBanner";
import { TermedBlock } from "./TermedBlock";

// The single discriminator switch -- every other component in this
// directory is dumb and type-narrowed, this is the only place that reads
// response_type. Data-driven, not string-matched against LLM prose (plan
// §1: "never raw LLM markdown").
export function ResultPanel({ result }: { result: CostEstimateResult }) {
  switch (result.response_type) {
    case "MEMBER_NOT_FOUND":
      return <MemberNotFoundBanner result={result} />;
    case "TERMED_BLOCK":
      return <TermedBlock result={result} />;
    case "EXCLUSION":
      return <ExclusionBanner result={result} />;
    case "RATE_NOT_FOUND":
      return <RateNotFoundBanner result={result} />;
    case "PREVENTIVE_ZERO_COST":
      return <PreventiveBanner result={result} />;
    case "STANDARD_COST":
      return <CostBreakdownTable result={result} />;
    case "NEEDS_CLARIFICATION":
      return <ClarificationPrompt result={result} />;
  }
}
