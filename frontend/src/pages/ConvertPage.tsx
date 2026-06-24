/**
 * Simple Convert Page for MVP
 * Clean upload-to-download experience
 */

import React, { useState, useEffect } from 'react';
import {
  useSuccessNotification,
  useErrorNotification,
} from '../components/NotificationSystem';
import { ConversionFlowManager } from '../components/ConversionFlow';
import { BatchConversionManager } from '../components/BatchConversion';
import {
  AdvancedOptionsPanel,
  AdvancedOptions,
} from '../components/AdvancedOptions';
import { ErrorBoundary } from '../components/ErrorBoundary/ErrorBoundary';
import { OnboardingFlow } from '../components/Onboarding/OnboardingFlow';
import { processError } from '../utils/conversionErrors';
import { ConfidenceBadge, ConfidenceMeter } from '../components/ui/confidence-badge';
import './ConvertPage.css';

const DEFAULT_ADVANCED_OPTIONS: AdvancedOptions = {
  timeout: 300,
  parallelProcessing: false,
  maxRetries: 3,
  enableSmartAssumptions: true,
  enableTextureOptimization: true,
  targetVersion: '1.20.0',
  generateReport: true,
};

export interface ConversionSummary {
  jobId: string;
  filename: string;
  status: 'completed' | 'failed' | 'partial';
  filesProcessed?: number;
  assetsConverted?: number;
  assetsTotal?: number;
  manualReviewFeatures?: string[];
  /** Aggregate confidence score computed from assumption data (0-1) */
  confidence?: number;
}

export const ConvertPage: React.FC = () => {
  const [conversionMode, setConversionMode] = useState<'single' | 'batch'>(
    'single'
  );
  const [advancedOptions, setAdvancedOptions] = useState<AdvancedOptions>(
    DEFAULT_ADVANCED_OPTIONS
  );
  const [lastConversionSummary, setLastConversionSummary] =
    useState<ConversionSummary | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Show onboarding for first-time visitors
  useEffect(() => {
    const completed = localStorage.getItem('onboarding_completed');
    if (completed !== 'true') {
      setShowOnboarding(true);
    }
  }, []);

  const successNotification = useSuccessNotification();
  const errorNotification = useErrorNotification();

  const handleOnboardingComplete = () => {
    setShowOnboarding(false);
  };

  const handleOnboardingClose = () => {
    setShowOnboarding(false);
  };

  const handleComplete = (jobId: string, filename: string) => {
    successNotification(
      'Conversion Complete!',
      `${filename} is ready for download.`
    );
    setLastConversionSummary({
      jobId,
      filename,
      status: 'completed',
    });
  };

  const handleError = (error: string) => {
    const friendlyError = processError(error);
    errorNotification(friendlyError.title, friendlyError.message);
  };

  const handleBatchComplete = (
    jobIds: string[],
    results?: { succeeded: number; failed: number }
  ) => {
    successNotification(
      'Batch Conversion Complete!',
      results
        ? `${results.succeeded} mods converted${results.failed > 0 ? `, ${results.failed} failed` : ''}.`
        : `${jobIds.length} mods converted successfully.`
    );
  };

  const handleBatchError = (error: string) => {
    const friendlyError = processError(error);
    errorNotification(friendlyError.title, friendlyError.message);
  };

  const clearConversionSummary = () => {
    setLastConversionSummary(null);
  };

  return (
    <div className="convert-page">
      <div className="convert-page-header">
        <h1>Mod Converter</h1>
        <p>Convert your Minecraft Java Edition mods to Bedrock Edition</p>
      </div>

      {/* Conversion Mode Tabs */}
      <div className="conversion-mode-tabs">
        <button
          className={`mode-tab ${conversionMode === 'single' ? 'active' : ''}`}
          onClick={() => setConversionMode('single')}
        >
          Single Conversion
        </button>
        <button
          className={`mode-tab ${conversionMode === 'batch' ? 'active' : ''}`}
          onClick={() => setConversionMode('batch')}
        >
          Batch Conversion
        </button>
      </div>

      {/* Advanced Options */}
      <div className="convert-page-options">
        <AdvancedOptionsPanel
          options={advancedOptions}
          onChange={setAdvancedOptions}
        />
      </div>

      {/* Conversion Flow */}
      {conversionMode === 'single' ? (
        <ErrorBoundary>
          <ConversionFlowManager
            onComplete={handleComplete}
            onError={handleError}
            showReport={true}
            autoReset={false}
          />
        </ErrorBoundary>
      ) : (
        <ErrorBoundary>
          <BatchConversionManager
            onComplete={handleBatchComplete}
            onError={handleBatchError}
          />
        </ErrorBoundary>
      )}

      {/* Conversion Summary Panel */}
      {lastConversionSummary && (
        <div className="conversion-summary-panel">
          <div className="summary-header">
            <h3>Last Conversion Summary</h3>
            <button
              className="summary-close"
              onClick={clearConversionSummary}
              aria-label="Close summary"
            >
              ✕
            </button>
          </div>
          <div className="summary-content">
            <div className="summary-item">
              <span className="summary-label">File:</span>
              <span className="summary-value">
                {lastConversionSummary.filename}
              </span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Status:</span>
              <span
                className={`summary-status ${lastConversionSummary.status}`}
              >
                {lastConversionSummary.status === 'completed' && '✓ Completed'}
                {lastConversionSummary.status === 'failed' && '✕ Failed'}
                {lastConversionSummary.status === 'partial' && '⚠ Partial'}
              </span>
            </div>
            {lastConversionSummary.confidence !== undefined && (
              <div className="summary-item">
                <span className="summary-label">Confidence:</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ConfidenceBadge
                    score={lastConversionSummary.confidence}
                    showPercentage={true}
                    size="sm"
                  />
                </div>
              </div>
            )}
            {lastConversionSummary.filesProcessed !== undefined && (
              <div className="summary-item">
                <span className="summary-label">Files Processed:</span>
                <span className="summary-value">
                  {lastConversionSummary.filesProcessed}
                </span>
              </div>
            )}
            {lastConversionSummary.assetsConverted !== undefined &&
              lastConversionSummary.assetsTotal !== undefined && (
                <div className="summary-item">
                  <span className="summary-label">Assets Converted:</span>
                  <span className="summary-value">
                    {lastConversionSummary.assetsConverted}/
                    {lastConversionSummary.assetsTotal}(
                    {Math.round(
                      (lastConversionSummary.assetsConverted /
                        lastConversionSummary.assetsTotal) *
                        100
                    )}
                    %)
                  </span>
                </div>
              )}
            {lastConversionSummary.manualReviewFeatures &&
              lastConversionSummary.manualReviewFeatures.length > 0 && (
                <div className="summary-item">
                  <span className="summary-label">Manual Review:</span>
                  <span className="summary-value">
                    {lastConversionSummary.manualReviewFeatures.join(', ')}
                  </span>
                </div>
              )}
          </div>
          <div className="summary-actions">
            <a
              href={`/api/v1/conversions/${lastConversionSummary.jobId}/download`}
              className="summary-download-btn"
              onClick={(e) => {
                if (lastConversionSummary.status === 'failed') {
                  e.preventDefault();
                }
              }}
            >
              Download .mcaddon
            </a>
          </div>
        </div>
      )}

      <div className="convert-page-footer">
        <div className="info-cards">
          <div className="info-card">
            <div className="card-icon">⚡</div>
            <h3>Fast Conversion</h3>
            <p>Most mods convert in under 5 minutes</p>
          </div>
          <div className="info-card">
            <div className="card-icon">🧠</div>
            <h3>Smart AI</h3>
            <p>Intelligent assumptions for better compatibility</p>
          </div>
          <div className="info-card">
            <div className="card-icon">📦</div>
            <h3>Ready to Use</h3>
            <p>Download .mcaddon files ready for Bedrock</p>
          </div>
        </div>
      </div>

      {/* Onboarding Flow for first-time visitors */}
      <OnboardingFlow
        isOpen={showOnboarding}
        onComplete={handleOnboardingComplete}
        onClose={handleOnboardingClose}
      />
    </div>
  );
};

export default ConvertPage;
