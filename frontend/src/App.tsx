
import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import DocsPage from "./pages/DocsPage";
import InterviewPage from "./pages/InterviewPage";
import RecruiterPage from "./pages/RecruiterPage";
import ResultsPage from "./pages/ResultsPage";
import { useTheme } from "./hooks/useTheme";
import "./styles/global.css";

const App: React.FC = () => {
  useTheme();

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RecruiterPage />} />
        <Route path="/interview/:sessionId" element={<InterviewPage />} />
        <Route path="/results/:sessionId" element={<ResultsPage />} />
        <Route path="/docs" element={<DocsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;

