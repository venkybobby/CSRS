import { DateOfServicePreview } from "./pages/DateOfServicePreview";
import { QueryPage } from "./pages/QueryPage";
import "./App.css";

export default function App() {
  // ?preview renders the date-of-service outcomes from fixtures, with no BFF
  // or agent running -- for reviewing the screens (and for demo capture)
  // without needing a live member whose coverage happens to end this month.
  if (typeof window !== "undefined" && window.location.search.includes("preview")) {
    return <DateOfServicePreview />;
  }
  return <QueryPage />;
}
