import { DateOfServicePreview } from "./pages/DateOfServicePreview";
import { DemoScriptPreview } from "./pages/DemoScriptPreview";
import { QueryPage } from "./pages/QueryPage";
import "./App.css";

export default function App() {
  // Fixture preview routes render from hardcoded results with no BFF and no
  // agent running -- for reviewing the screens (and for demo capture)
  // without needing a live deployment, or a member whose coverage happens to
  // end this month.
  //
  //   ?preview       date-of-service outcomes + the prior-auth banner
  //   ?preview=demo  demo-script cases 1-5
  //
  // Read via URLSearchParams rather than a substring test on the query
  // string, so `?preview` and `?preview=demo` are distinguishable at all --
  // and so a genuine query param that merely contains "preview" can't route
  // a CSR into a fixture page showing figures for members they didn't ask
  // about.
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    if (params.has("preview")) {
      return params.get("preview") === "demo" ? <DemoScriptPreview /> : <DateOfServicePreview />;
    }
  }
  return <QueryPage />;
}
