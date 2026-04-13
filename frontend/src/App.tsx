import { Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import Layout from "./components/Layout";
import JournalPage from "./pages/JournalPage";
import ProfilePage from "./pages/ProfilePage";
import QuizPage from "./pages/QuizPage";
import ReadingsPage from "./pages/ReadingsPage";
import ProjectsPage from "./pages/ProjectsPage";
import TriagePage from "./pages/TriagePage";
import SettingsPage from "./pages/SettingsPage";
import OnboardingPage from "./pages/OnboardingPage";
import { api } from "./api/client";

export default function App() {
  const [onboardingDone, setOnboardingDone] = useState<boolean | null>(null);

  useEffect(() => {
    api.onboarding
      .getState()
      .then((state) => {
        setOnboardingDone(state.completed);
      })
      .catch(() => {
        // If API is unreachable, assume onboarding not done
        setOnboardingDone(false);
      });
  }, []);

  if (onboardingDone === null) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-lg text-gray-500">Loading…</div>
      </div>
    );
  }

  if (!onboardingDone) {
    return (
      <Routes>
        <Route
          path="/onboarding"
          element={
            <OnboardingPage onComplete={() => setOnboardingDone(true)} />
          }
        />
        <Route path="*" element={<Navigate to="/onboarding" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/journal" replace />} />
        <Route path="/journal" element={<JournalPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/quiz" element={<QuizPage />} />
        <Route path="/readings" element={<ReadingsPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/triage" element={<TriagePage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/journal" replace />} />
    </Routes>
  );
}
