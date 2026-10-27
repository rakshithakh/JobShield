import { Link, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import { ToastProvider } from "./components/ui";
import LandingPage from "./pages/LandingPage";
import AnalyzePage from "./pages/AnalyzePage";
import ResultPage from "./pages/ResultPage";
import HistoryPage from "./pages/HistoryPage";
import DashboardPage from "./pages/DashboardPage";
import AboutPage from "./pages/AboutPage";
import DemoPage from "./pages/DemoPage";

function NotFound() {
  return <div className="space-y-3"><h1 className="text-4xl">Page not found</h1><Link className="font-semibold underline" to="/">Go to the home page</Link></div>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<LandingPage />} />
            <Route path="analyze" element={<AnalyzePage />} />
            <Route path="analyses/:id" element={<ResultPage />} />
            <Route path="history" element={<HistoryPage />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="demo" element={<DemoPage />} />
            <Route path="about" element={<AboutPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </ToastProvider>
    </ErrorBoundary>
  );
}
