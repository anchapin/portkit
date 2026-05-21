import React, { Suspense, lazy, useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import { NotificationProvider } from './components/NotificationSystem';
import { TopNavigation } from './components/TopNavigation';
import { OnboardingFlow } from './components/Onboarding';
import { CookieConsentBanner } from './components/common/CookieConsentBanner';
import { PageViewTracker } from './components/PageViewTracker';
// import { usePageViewTracking } from './hooks/useAnalytics'; // Temporarily disabled pending PageViewTracker integration
import './App.css';
import './components/common/CookieConsentBanner.css';

// Lazy load heavy components
// Using type assertion to handle named exports
const DocumentationSimple = lazy(() =>
  import('./pages/DocumentationSimple').then((m) => ({
    default: m.DocumentationSimple as React.ComponentType<any>,
  }))
);
const Dashboard = lazy(() => import('./pages/Dashboard'));
const LandingPage = lazy(() => import('./pages/LandingPage'));
const ConvertPage = lazy(() => import('./pages/ConvertPage'));
const ComparisonView = lazy(() =>
  import('./components/ComparisonView').then((m) => ({
    default: m.ComparisonView as React.ComponentType<any>,
  }))
);
const BehavioralTestWrapper = lazy(() =>
  import('./components/BehavioralTest/BehavioralTestWrapper').then((m) => ({
    default: m.BehavioralTestWrapper as React.ComponentType<any>,
  }))
);
const EditorPage = lazy(() => import('./pages/EditorPage'));
const ExperimentsPage = lazy(() => import('./pages/ExperimentsPage'));
const ExperimentResultsPage = lazy(
  () => import('./pages/ExperimentResultsPage')
);
const Settings = lazy(() => import('./pages/Settings'));
const PricingPage = lazy(() => import('./pages/PricingPage'));
const UploadPage = lazy(() => import('./pages/UploadPage'));
const ProgressPage = lazy(() => import('./pages/ProgressPage'));
const ResultsPage = lazy(() => import('./pages/ResultsPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const OAuthCallbackPage = lazy(() => import('./pages/OAuthCallbackPage'));
const TermsPage = lazy(() => import('./pages/TermsPage'));
const PrivacyPage = lazy(() => import('./pages/PrivacyPage'));
const CookiesPage = lazy(() => import('./pages/CookiesPage'));
const DataSubjectRequestPage = lazy(() =>
  import('./pages/DataSubjectRequestPage').then((m) => ({
    default: m.DataSubjectRequestPage as React.ComponentType<any>,
  }))
);
const IPPolicyPage = lazy(() => import('./pages/IPPolicyPage'));
const StatusPage = lazy(() => import('./pages/StatusPage'));
const ShowcasePage = lazy(() => import('./pages/ShowcasePage'));

function App() {
  console.log('App component is rendering...');

  // Onboarding state
  const [showOnboarding, setShowOnboarding] = useState(false);

  useEffect(() => {
    // TEMPORARILY DISABLED: Onboarding flow is disabled
    // New users should be directed to sign up for waitlist instead
    // To re-enable: change the logic back to check for !onboardingCompleted
    setShowOnboarding(false);
  }, []);

  return (
    <ErrorBoundary>
      <NotificationProvider>
        <Router>
          <PageViewTracker />
          <div className="app">
            <OnboardingFlow
              isOpen={showOnboarding}
              onComplete={() => setShowOnboarding(false)}
              onClose={() => setShowOnboarding(false)}
            />
            <TopNavigation />
            <CookieConsentBanner />

            <main>
              <Routes>
                <Route
                  path="/"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <LandingPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/convert"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <ConvertPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/dashboard"
                  element={
                    <Suspense fallback={<div>Loading Dashboard...</div>}>
                      <Dashboard />
                    </Suspense>
                  }
                />
                <Route
                  path="/experiments"
                  element={
                    <Suspense fallback={<div>Loading Experiments...</div>}>
                      <ExperimentsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/experiment-results"
                  element={
                    <Suspense fallback={<div>Loading Results...</div>}>
                      <ExperimentResultsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/comparison"
                  element={
                    <Suspense fallback={<div>Loading Comparison...</div>}>
                      <div className="page-wrapper">
                        <ComparisonView />
                      </div>
                    </Suspense>
                  }
                />
                <Route
                  path="/comparison/:comparisonId"
                  element={
                    <Suspense fallback={<div>Loading Comparison...</div>}>
                      <div className="page-wrapper">
                        <ComparisonView />
                      </div>
                    </Suspense>
                  }
                />
                <Route
                  path="/behavioral-test/:conversionId"
                  element={
                    <Suspense fallback={<div>Loading Behavioral Test...</div>}>
                      <div className="page-wrapper">
                        <BehavioralTestWrapper />
                      </div>
                    </Suspense>
                  }
                />
                <Route
                  path="/docs"
                  element={
                    <Suspense fallback={<div>Loading Documentation...</div>}>
                      <DocumentationSimple />
                    </Suspense>
                  }
                />
                <Route
                  path="/editor/:addonId"
                  element={
                    <Suspense fallback={<div>Loading Editor...</div>}>
                      <EditorPage />
                    </Suspense>
                  }
                />{' '}
                {/* Added Editor Route */}
                <Route
                  path="/behavior-editor/:conversionId"
                  element={
                    <Suspense fallback={<div>Loading Behavior Editor...</div>}>
                      <EditorPage />
                    </Suspense>
                  }
                />{' '}
                {/* Added Behavior Editor Route */}
                <Route
                  path="/settings"
                  element={
                    <Suspense fallback={<div>Loading Settings...</div>}>
                      <Settings />
                    </Suspense>
                  }
                />
                <Route
                  path="/pricing"
                  element={
                    <Suspense fallback={<div>Loading Pricing...</div>}>
                      <PricingPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/upload"
                  element={
                    <Suspense fallback={<div>Loading Upload...</div>}>
                      <UploadPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/progress/:jobId"
                  element={
                    <Suspense fallback={<div>Loading Progress...</div>}>
                      <ProgressPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/results/:jobId"
                  element={
                    <Suspense fallback={<div>Loading Results...</div>}>
                      <ResultsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/login"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <LoginPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/auth/callback/:provider"
                  element={
                    <Suspense fallback={<div>Processing...</div>}>
                      <OAuthCallbackPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/terms"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <TermsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/privacy"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <PrivacyPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/privacy/request"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <DataSubjectRequestPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/cookies"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <CookiesPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/ip-policy"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <IPPolicyPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/status"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <StatusPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/showcase"
                  element={
                    <Suspense fallback={<div>Loading...</div>}>
                      <ShowcasePage />
                    </Suspense>
                  }
                />
              </Routes>
            </main>
          </div>
        </Router>
      </NotificationProvider>
    </ErrorBoundary>
  );
}

export default App;
