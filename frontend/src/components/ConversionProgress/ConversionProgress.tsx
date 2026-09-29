import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ConversionStatus } from '../../types/api';
import { getConversionStatus } from '../../services/api'; // Import the API service
import './ConversionProgress.css';

// SVG icons as inline components for better compatibility
const CheckmarkIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    width="14px"
    height="14px"
  >
    <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
  </svg>
);

const PendingIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    width="14px"
    height="14px"
  >
    <circle cx="12" cy="12" r="10" />
  </svg>
);

const SpinnerIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    width="14px"
    height="14px"
    className="spinner-icon"
  >
    <path
      d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z"
      opacity="0.3"
    />
    <path d="M12 2v4c3.31 0 6 2.69 6 6h4c0-5.52-4.48-10-10-10z" />
  </svg>
);

// Agent status interface for detailed tracking
interface AgentStatus {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  message?: string;
}

// Extended conversion status with agent details
interface ExtendedConversionStatus extends ConversionStatus {
  agents?: AgentStatus[];
  current_agent?: string;
}

// Define the props for the component
export interface ConversionProgressProps {
  jobId: string | null;
  status?: string;
  progress?: number;
  message?: string;
  stage?: string | null;
  /** Fires when conversion reaches a terminal state (completed/failed/cancelled). */
  onTerminalState?: (
    jobId: string,
    status: 'completed' | 'failed' | 'cancelled',
    error?: string
  ) => void;
}

const ConversionProgress: React.FC<ConversionProgressProps> = ({
  jobId,
  status,
  progress,
  message,
  stage,
  onTerminalState,
}) => {
  // Define the steps for the conversion process
  const conversionSteps = ['Queued', 'Processing', 'Completed'];

  // Initialize all hooks first before any early returns
  const [progressData, setProgressData] = useState<ConversionStatus>({
    job_id: jobId || '',
    status: status || 'queued',
    progress: progress || 0,
    message: message || 'Processing...',
    stage: stage || 'Queued', // Default to 'Queued'
    estimated_time_remaining: null,
    result_url: null,
    error: null,
    created_at: new Date().toISOString(),
  });

  const [usingWebSocket, setUsingWebSocket] = useState<boolean>(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentStatus[]>([]);

  const webSocketRef = useRef<WebSocket | null>(null);
  const pollingIntervalRef = useRef<number | null>(null);
  const currentStatusRef = useRef<string>('queued');
  const reconnectTimeoutRef = useRef<number | null>(null);

  // Maximum reconnection attempts before falling back to polling
  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_DELAY_BASE = 1000; // 1 second base delay

  // Use same logic as api.ts for consistency
  // Priority: VITE_API_BASE_URL > VITE_API_URL > default to relative path
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
    ? import.meta.env.VITE_API_BASE_URL + '/api/v1'
    : import.meta.env.VITE_API_URL
      ? import.meta.env.VITE_API_URL.replace(/\/api\/v1$/, '') + '/api/v1'
      : '/api/v1';

  // Extract base URL (without /api/v1) and convert to WebSocket protocol
  const wsBaseUrl = API_BASE_URL.replace(/\/api\/v1$/, '')
    .replace(/^http:/, 'ws:')
    .replace(/^https:/, 'wss:');

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      window.clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
      console.log('Polling stopped.');
    }
  };

  const clearReconnectTimeout = () => {
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  };

  // Calculate exponential backoff delay
  const getReconnectDelay = (attempt: number): number => {
    // Exponential backoff: 1s, 2s, 4s, 8s, 16s (max)
    return Math.min(RECONNECT_DELAY_BASE * Math.pow(2, attempt), 16000);
  };

  const updateProgressData = useCallback(
    (newData: ConversionStatus) => {
      setProgressData(newData);
      currentStatusRef.current = newData.status;
      if (
        newData.status === 'completed' ||
        newData.status === 'failed' ||
        newData.status === 'cancelled'
      ) {
        console.log(
          `Conversion ended with status: ${newData.status}. Cleaning up connections.`
        );
        if (
          webSocketRef.current &&
          webSocketRef.current.readyState === WebSocket.OPEN
        ) {
          webSocketRef.current.close(1000, `Conversion ${newData.status}`);
        }
        if (pollingIntervalRef.current) {
          window.clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        setUsingWebSocket(false); // Ensure this is reset

        // Fire terminal state callback so parent can handle completion/failure
        if (onTerminalState) {
          onTerminalState(
            jobId || newData.job_id,
            newData.status,
            newData.error || newData.message
          );
        }
      }
    },
    [jobId, onTerminalState]
  );

  const startPolling = useCallback(() => {
    // Prevent multiple polling intervals
    stopPolling();
    console.log(
      `WebSocket failed or not supported. Falling back to polling for ${jobId}.`
    );
    setUsingWebSocket(false);

    pollingIntervalRef.current = window.setInterval(async () => {
      try {
        const status = await getConversionStatus(jobId);
        console.log('Polling: Fetched status:', status);
        updateProgressData(status);
        setConnectionError(null); // Clear previous errors if polling succeeds
      } catch (error) {
        console.error('Polling error:', error);
        setConnectionError('Failed to fetch conversion status. Retrying...');
        // Optional: Implement max retries for polling or different error handling
      }
    }, 3000); // Poll every 3 seconds
  }, [jobId, updateProgressData]);

  useEffect(() => {
    // Cleanup function to be called when component unmounts or conversionId changes
    const cleanup = () => {
      console.log(`Cleaning up resources for conversion ID: ${jobId}`);
      clearReconnectTimeout();
      if (webSocketRef.current) {
        webSocketRef.current.onclose = null; // Avoid triggering onclose logic during cleanup
        webSocketRef.current.onerror = null;
        webSocketRef.current.close(1000, 'Component unmounting or ID changed');
        webSocketRef.current = null;
      }
      stopPolling();
      setProgressData({
        // Reset state
        job_id: jobId,
        status: status || 'queued',
        progress: progress || 0,
        message: message || 'Initializing...',
        stage: stage || 'Queued',
        estimated_time_remaining: null,
        result_url: null,
        error: null,
        created_at: new Date().toISOString(),
      });
      setUsingWebSocket(false);
      setConnectionError(null);
      setAgents([]);
    };

    cleanup(); // Clean up previous connection/polling before starting new one

    const connectWebSocket = (attempt: number = 0) => {
      // Check if we've exceeded max reconnection attempts
      if (attempt >= MAX_RECONNECT_ATTEMPTS) {
        console.log(
          `Max reconnection attempts (${MAX_RECONNECT_ATTEMPTS}) reached. Falling back to polling.`
        );
        setConnectionError(
          `Unable to establish WebSocket connection after ${MAX_RECONNECT_ATTEMPTS} attempts. Using polling fallback.`
        );
        startPolling();
        return;
      }

      const wsUrl = `${wsBaseUrl}/ws/v1/convert/${jobId}/progress`;
      console.log(
        `Attempting to connect WebSocket (attempt ${attempt + 1}/${MAX_RECONNECT_ATTEMPTS}): ${wsUrl}`
      );
      const ws = new WebSocket(wsUrl);
      webSocketRef.current = ws;

      ws.onopen = () => {
        console.log(`WebSocket connected for ${jobId}`);
        setUsingWebSocket(true);
        setConnectionError(null); // Clear any previous errors
        stopPolling(); // Stop polling if WebSocket connects successfully
        clearReconnectTimeout();
        // Optionally, fetch initial status once via HTTP to ensure no missed updates
        getConversionStatus(jobId)
          .then(updateProgressData)
          .catch(console.error);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string);
          // The server sends the full ConversionStatus object as a JSON string
          console.log('WebSocket message received:', data);

          // Handle extended status with agent information
          const extendedData = data as ExtendedConversionStatus;
          if (extendedData.agents) {
            setAgents(extendedData.agents);
          }

          updateProgressData(data as ConversionStatus);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error(`WebSocket error for ${jobId}:`, error);
        // Don't setConnectionError here, as onclose will handle fallback
      };

      ws.onclose = (event) => {
        console.log(
          `WebSocket closed for ${jobId}. Code: ${event.code}, Reason: ${event.reason}`
        );
        webSocketRef.current = null; // Clear the ref

        // Only attempt reconnection if the closure was unexpected and not a terminal state
        if (
          currentStatusRef.current !== 'completed' &&
          currentStatusRef.current !== 'failed' &&
          currentStatusRef.current !== 'cancelled'
        ) {
          const nextAttempt = attempt + 1;

          if (nextAttempt < MAX_RECONNECT_ATTEMPTS) {
            const delay = getReconnectDelay(attempt);
            console.log(
              `Scheduling WebSocket reconnection attempt ${nextAttempt + 1} in ${delay}ms`
            );
            setConnectionError(
              `Connection lost. Reconnecting in ${Math.round(delay / 1000)}s... (attempt ${nextAttempt + 1}/${MAX_RECONNECT_ATTEMPTS})`
            );

            reconnectTimeoutRef.current = window.setTimeout(() => {
              connectWebSocket(nextAttempt);
            }, delay);
          } else {
            // Fall back to polling after max attempts
            setConnectionError(
              'WebSocket connection failed. Using polling fallback.'
            );
            startPolling();
          }
        } else {
          setUsingWebSocket(false); // Ensure this is reset for terminal states
        }
      };
    };

    // Initial connection attempt
    connectWebSocket(0);

    return cleanup; // Return the cleanup function
  }, [
    jobId,
    wsBaseUrl,
    updateProgressData,
    startPolling,
    message,
    progress,
    stage,
    status,
  ]); // Re-run effect if dependencies change

  if (!jobId) {
    return (
      <div className="conversion-progress-container">
        <p>No conversion in progress</p>
      </div>
    );
  }

  const handleDownload = () => {
    if (progressData.result_url) {
      const downloadUrl = progressData.result_url.startsWith('http')
        ? progressData.result_url
        : `${API_BASE_URL}${progressData.result_url}`;
      window.open(downloadUrl, '_blank');
    }
  };

  let statusMessage = progressData.message;
  if (connectionError && !usingWebSocket) {
    statusMessage = connectionError;
  } else if (usingWebSocket && progressData.message) {
    statusMessage = `Connected via WebSocket. ${progressData.message}`;
  } else if (usingWebSocket) {
    statusMessage = 'Connected via WebSocket. Processing...';
  }

  // Determine the current step index
  // This is a simplified mapping. A more robust solution might be needed.
  let currentStepIndex = conversionSteps.indexOf(
    progressData.stage || 'Queued'
  );
  if (currentStepIndex === -1) {
    if (progressData.status === 'completed') {
      currentStepIndex = conversionSteps.length - 1;
    } else if (
      progressData.status === 'failed' ||
      progressData.status === 'cancelled'
    ) {
      // Handle error/cancelled state - perhaps show all steps as pending or a specific error step
      // For now, let's assume it stays at the last known stage or resets.
      // Or find the last non-completed step if stages are dynamic from backend.
      // Setting to 0 for now if stage is unknown and not completed/failed.
      currentStepIndex = 0; // Default to first step if stage is unrecognized
    } else {
      currentStepIndex = 0; // Default for unknown stages if not terminal
    }
  }
  // If status is 'completed', all steps up to "Completed" are done.
  // If status is 'failed', we might want to show the step it failed on.
  // For this implementation, 'Completed' stage implies all steps are done.
  if (progressData.status === 'completed') {
    currentStepIndex = conversionSteps.indexOf('Completed');
  }

  return (
    <div className="conversion-progress-container">
      <h4>Conversion Progress{jobId ? ` (ID: ${jobId})` : ''}</h4>

      {/* Connection Status Indicator */}
      <div className="connection-status">
        <div
          className={`connection-indicator ${usingWebSocket ? '' : 'polling'}${connectionError ? ' error' : ''}`}
        ></div>
        <span>
          {usingWebSocket
            ? 'Real-time updates active'
            : connectionError
              ? 'Connection issues'
              : 'Using fallback polling'}
        </span>
      </div>

      {/* Progress Steps */}
      <ul className="conversion-steps-list">
        {conversionSteps.map((step, index) => {
          // Determine step completion status
          let stepCompleted = index < currentStepIndex;
          if (progressData.status === 'completed' && step === 'Completed') {
            stepCompleted = true;
          }

          // Determine if this is the current/active step
          const isCurrent =
            index === currentStepIndex &&
            progressData.status !== 'completed' &&
            progressData.status !== 'failed';

          return (
            <li
              key={step}
              className={`conversion-step ${isCurrent ? 'current' : ''} ${stepCompleted ? 'completed' : 'pending'}`}
            >
              <div className="step-icon">
                {stepCompleted ? <CheckmarkIcon /> : <PendingIcon />}
              </div>
              <div className="step-name">{step}</div>
            </li>
          );
        })}
      </ul>

      {/* Agent-Level Progress (if available) */}
      {agents.length > 0 && (
        <div className="agents-progress">
          <h5>Agent Progress</h5>
          <div className="agents-list">
            {agents.map((agent, index) => (
              <div key={index} className={`agent-item agent-${agent.status}`}>
                <div className="agent-header">
                  <div className="agent-icon">
                    {agent.status === 'completed' && <CheckmarkIcon />}
                    {agent.status === 'running' && <SpinnerIcon />}
                    {agent.status === 'pending' && <PendingIcon />}
                    {agent.status === 'failed' && (
                      <span className="error-icon">✕</span>
                    )}
                  </div>
                  <span className="agent-name">{agent.name}</span>
                  <span className="agent-status">{agent.status}</span>
                </div>
                {agent.status === 'running' && (
                  <div className="agent-progress-bar">
                    <div
                      className="agent-progress-fill"
                      style={{ width: `${Math.min(agent.progress, 100)}%` }}
                    />
                  </div>
                )}
                {agent.message && (
                  <div className="agent-message">{agent.message}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Overall Progress Bar */}
      <div className="progress-bar-container">
        <div
          className={`progress-bar-fill ${progressData.status === 'completed' ? 'progress-bar-filler' : ''}`}
          role="progressbar"
          aria-valuenow={Math.min(progressData.progress, 100)}
          aria-valuemin="0"
          aria-valuemax="100"
          style={{ width: `${Math.min(progressData.progress, 100)}%` }}
        >
          {Math.round(Math.min(progressData.progress, 100))}%
        </div>
      </div>

      {/* Status Message */}
      <div className="status-message">
        <strong>Status:</strong> {progressData.status}
      </div>

      {/* Stage Information */}
      {progressData.stage && (
        <div className="stage-message">
          <strong>Stage:</strong> {progressData.stage}
        </div>
      )}

      {/* Estimated Time Remaining */}
      <div className="time-remaining">
        <strong>Estimated Time Remaining:</strong>{' '}
        {progressData.estimated_time_remaining || 'N/A'}
      </div>

      {statusMessage &&
        statusMessage !== progressData.status &&
        progressData.status !== 'failed' && (
          <div className="additional-message">
            <strong>Message:</strong> {statusMessage}
          </div>
        )}

      {/* Connection Error */}
      {connectionError && (
        <div className="connection-error-message">
          <strong>Connection Issue:</strong> {connectionError}
        </div>
      )}

      {/* Download Button */}
      {progressData.status === 'completed' && progressData.result_url && (
        <button onClick={handleDownload} className="download-button">
          <span>📥</span>
          Download Converted File
        </button>
      )}

      {/* Error Display */}
      {progressData.status === 'failed' && (
        <div className="error-message">
          <p>
            <strong>Error:</strong>{' '}
            {progressData.error ||
              progressData.message ||
              'An unknown error occurred.'}
          </p>
          {progressData.message &&
            progressData.message !== progressData.error &&
            progressData.error && (
              <p>
                <strong>Details:</strong> {progressData.message}
              </p>
            )}
        </div>
      )}
    </div>
  );
};

export default ConversionProgress;
