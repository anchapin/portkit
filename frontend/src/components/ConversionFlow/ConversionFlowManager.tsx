/**
 * Conversion Flow Manager
 * Orchestrates the complete upload-to-download experience
 * Handles state management, progress tracking, and error recovery
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import * as Sentry from '@sentry/react';
import { ConversionUploadEnhanced } from '../ConversionUpload/ConversionUploadEnhanced';
import ConversionProgress from '../ConversionProgress/ConversionProgress';
import { ConversionReportContainer } from '../ConversionReport/ConversionReportContainer';
import {
  useSuccessNotification,
  useErrorNotification,
} from '../NotificationSystem';
import { processError, UserFriendlyError } from '../../utils/conversionErrors';
import { triggerDownload } from '../../services/api';
import { useConversionTracking } from '../../hooks/useAnalytics';
import './ConversionFlowManager.css';

export interface ConversionFlowState {
  jobId: string | null;
  filename: string;
  status:
    | 'idle'
    | 'uploading'
    | 'converting'
    | 'completed'
    | 'failed'
    | 'cancelled';
  progress: number;
  error: string | null;
  resultUrl: string | null;
  friendlyError?: UserFriendlyError;
}

interface ConversionFlowManagerProps {
  onComplete?: (jobId: string, filename: string) => void;
  onError?: (error: string) => void;
  showReport?: boolean;
  autoReset?: boolean;
  resetDelay?: number;
}

export const ConversionFlowManager: React.FC<ConversionFlowManagerProps> = ({
  onComplete,
  onError,
  showReport = true,
  autoReset = false,
  resetDelay = 30000,
}) => {
  const [flowState, setFlowState] = useState<ConversionFlowState>({
    jobId: null,
    filename: '',
    status: 'idle',
    progress: 0,
    error: null,
    resultUrl: null,
  });

  const resetTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const successNotification = useSuccessNotification();
  const errorNotification = useErrorNotification();

  // Analytics tracking
  const { trackStart, trackComplete, trackFail, trackDownload } =
    useConversionTracking();

  // Clear any pending reset timeout
  useEffect(() => {
    return () => {
      if (resetTimeoutRef.current) {
        clearTimeout(resetTimeoutRef.current);
      }
    };
  }, []);

  // Reset flow state
  const resetFlow = useCallback(() => {
    if (resetTimeoutRef.current) {
      clearTimeout(resetTimeoutRef.current);
      resetTimeoutRef.current = null;
    }

    setFlowState({
      jobId: null,
      filename: '',
      status: 'idle',
      progress: 0,
      error: null,
      resultUrl: null,
    });
  }, []);

  // Handle conversion start
  const handleConversionStart = useCallback(
    (jobId: string, filename: string) => {
      // Track conversion start
      trackStart(jobId, { filename });

      setFlowState({
        jobId,
        filename,
        status: 'converting',
        progress: 0,
        error: null,
        resultUrl: null,
      });
    },
    [trackStart]
  );

  // Handle conversion complete
  const handleConversionComplete = useCallback(
    (jobId: string) => {
      // Track conversion complete
      trackComplete(jobId, { filename: flowState.filename });

      setFlowState((prev) => ({
        ...prev,
        status: 'completed',
        progress: 100,
        resultUrl: `/api/v1/conversions/${jobId}/download`,
      }));

      // Show success toast
      successNotification(
        'Conversion Complete!',
        `${flowState.filename} is ready for download.`
      );

      if (onComplete) {
        onComplete(jobId, flowState.filename);
      }

      // Auto-reset if enabled
      if (autoReset) {
        resetTimeoutRef.current = setTimeout(() => {
          resetFlow();
        }, resetDelay);
      }
    },
    [
      flowState.filename,
      onComplete,
      autoReset,
      resetDelay,
      resetFlow,
      trackComplete,
      successNotification,
    ]
  );

  // Handle conversion failed
  const handleConversionFailed = useCallback(
    (jobId: string, error: string) => {
      // Process error for user-friendly message
      const friendlyError = processError(error);

      // Report to Sentry if needed
      if (friendlyError.reportToSentry) {
        Sentry.captureException(new Error(error), {
          tags: { errorType: friendlyError.type },
          extra: {
            jobId,
            filename: flowState.filename,
            originalError: error,
          },
        });
      }

      // Track conversion fail
      trackFail(jobId, { error: error.substring(0, 200) });

      setFlowState((prev) => ({
        ...prev,
        status: 'failed',
        error,
        friendlyError,
      }));

      // Show error toast
      errorNotification(friendlyError.title, friendlyError.message);

      if (onError) {
        onError(error);
      }
    },
    [flowState.filename, onError, trackFail, errorNotification]
  );

  // Handle manual download
  const handleDownload = useCallback(async () => {
    if (!flowState.jobId) return;

    try {
      // ⚡ Bolt optimization: Use triggerDownload to prevent large memory spikes from blob allocation
      await triggerDownload(flowState.jobId);

      // Track download
      trackDownload(flowState.jobId, { filename: flowState.filename });
    } catch (error: any) {
      const downloadErrorMsg =
        error.message || 'Download failed. Please try again.';
      errorNotification('Download Failed', downloadErrorMsg);
      setFlowState((prev) => ({
        ...prev,
        error: downloadErrorMsg,
      }));
    }
  }, [flowState.jobId, flowState.filename, trackDownload, errorNotification]);

  // Render upload component when idle
  if (flowState.status === 'idle') {
    return (
      <div className="conversion-flow-manager">
        <ConversionUploadEnhanced
          onConversionStart={handleConversionStart}
          onConversionComplete={handleConversionComplete}
          onConversionFailed={handleConversionFailed}
        />
      </div>
    );
  }

  // Render progress during conversion
  if (flowState.status === 'uploading' || flowState.status === 'converting') {
    return (
      <div className="conversion-flow-manager">
        <div className="conversion-flow-progress">
          <div className="flow-header">
            <h2>Converting {flowState.filename}</h2>
            <button
              className="reset-button"
              onClick={resetFlow}
              title="Cancel and start over"
              aria-label="Cancel conversion"
            >
              <span aria-hidden="true">✕</span>
            </button>
          </div>

          {flowState.jobId && (
            <ConversionProgress
              jobId={flowState.jobId}
              onTerminalState={(jobId, status, error) => {
                if (status === 'completed') {
                  handleConversionComplete(jobId);
                } else if (status === 'failed') {
                  handleConversionFailed(jobId, error || 'Conversion failed');
                }
                // cancelled: stay in converting view, user can reset
              }}
            />
          )}

          {/* Progress Summary */}
          <div className="progress-summary">
            <div className="summary-item">
              <span className="label">Status:</span>
              <span className="value">{flowState.status}</span>
            </div>
            {flowState.jobId && (
              <div className="summary-item">
                <span className="label">Job ID:</span>
                <span className="value mono">{flowState.jobId}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Render completion screen
  if (flowState.status === 'completed') {
    return (
      <div className="conversion-flow-manager">
        <div className="conversion-flow-complete">
          <div className="success-animation">
            <div className="checkmark">✓</div>
          </div>

          <h2>Conversion Complete!</h2>
          <p className="filename">{flowState.filename}</p>

          <div className="action-buttons">
            <button
              className="download-button primary"
              onClick={handleDownload}
            >
              <span className="icon" aria-hidden="true">
                ⬇
              </span>
              Download .mcaddon
            </button>

            {showReport && flowState.jobId && (
              <button
                className="report-button secondary"
                onClick={() => {
                  // Scroll to report
                  const reportElement = document.getElementById(
                    `conversion-report-${flowState.jobId}`
                  );
                  if (reportElement) {
                    reportElement.scrollIntoView({ behavior: 'smooth' });
                  }
                }}
              >
                <span className="icon" aria-hidden="true">
                  📋
                </span>
                View Report
              </button>
            )}

            <button className="reset-button tertiary" onClick={resetFlow}>
              <span className="icon" aria-hidden="true">
                🔄
              </span>
              Convert Another
            </button>
          </div>

          {showReport && flowState.jobId && (
            <div
              id={`conversion-report-${flowState.jobId}`}
              className="flow-report"
            >
              <ConversionReportContainer
                jobId={flowState.jobId}
                jobStatus="completed"
              />
            </div>
          )}

          {autoReset && (
            <div className="auto-reset-notice">
              Page will reset in {Math.ceil(resetDelay / 1000)} seconds...
            </div>
          )}
        </div>
      </div>
    );
  }

  // Render error screen
  if (flowState.status === 'failed') {
    const friendlyError = flowState.friendlyError;
    const errorTips = friendlyError?.userTips || [
      'Check that the file is a valid .jar or .zip archive',
      'Ensure the file is not corrupted',
      'Try enabling "Smart Assumptions" for better compatibility',
      'For large modpacks, try converting with fewer mods first',
    ];

    return (
      <div className="conversion-flow-manager">
        <div className="conversion-flow-error">
          <div className="error-animation">
            <div className="error-icon">✕</div>
          </div>

          <h2>{friendlyError?.title || 'Conversion Failed'}</h2>
          <p className="filename">{flowState.filename}</p>

          {friendlyError && (
            <div className="error-message">
              <p>{friendlyError.message}</p>
            </div>
          )}

          {!friendlyError && flowState.error && (
            <div className="error-message">
              <strong>Error:</strong>
              <p>{flowState.error}</p>
            </div>
          )}

          <div className="error-tips">
            <h4>What you can try:</h4>
            <ul>
              {errorTips.map((tip, index) => (
                <li key={index}>{tip}</li>
              ))}
            </ul>
          </div>

          <div className="action-buttons">
            {friendlyError?.retryable && (
              <button className="retry-button primary" onClick={resetFlow}>
                <span className="icon" aria-hidden="true">
                  🔄
                </span>
                Try Again
              </button>
            )}

            {!friendlyError?.retryable && (
              <button className="retry-button primary" onClick={resetFlow}>
                <span className="icon" aria-hidden="true">
                  🔄
                </span>
                Try Again
              </button>
            )}

            {flowState.jobId && (
              <button
                className="report-button secondary"
                onClick={() => {
                  // Even failed conversions might have partial reports
                  const reportElement = document.getElementById(
                    `conversion-report-${flowState.jobId}`
                  );
                  if (reportElement) {
                    reportElement.scrollIntoView({ behavior: 'smooth' });
                  }
                }}
              >
                <span className="icon" aria-hidden="true">
                  📋
                </span>
                View Partial Report
              </button>
            )}
          </div>

          {showReport && flowState.jobId && (
            <div
              id={`conversion-report-${flowState.jobId}`}
              className="flow-report"
            >
              <ConversionReportContainer
                jobId={flowState.jobId}
                jobStatus="failed"
              />
            </div>
          )}
        </div>
      </div>
    );
  }

  // Render cancelled screen
  if (flowState.status === 'cancelled') {
    return (
      <div className="conversion-flow-manager">
        <div className="conversion-flow-cancelled">
          <h2>Conversion Cancelled</h2>
          <p>The conversion was cancelled.</p>

          <button className="reset-button primary" onClick={resetFlow}>
            Start New Conversion
          </button>
        </div>
      </div>
    );
  }

  return null;
};

export default ConversionFlowManager;
