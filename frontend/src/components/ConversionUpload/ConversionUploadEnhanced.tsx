/**
 * Enhanced ConversionUpload Component
 * Improved WebSocket integration and better UX for MVP
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import {
  convertMod,
  getConversionStatus,
  cancelJob,
  triggerDownload,
} from '../../services/api';
import { createConversionWebSocket } from '../../services/websocket';
import {
  InitiateConversionParams,
  ConversionResponse,
  ConversionStatus,
  ConversionStatusEnum,
} from '../../types/api';
import { useErrorNotification } from '../NotificationSystem';
import ConversionOptions from './ConversionOptions';
import './ConversionUpload.css';

// Configuration constants
const MAX_FILE_SIZE_MB = 500;

interface ConversionUploadProps {
  onConversionStart?: (jobId: string, filename: string) => void;
  onConversionComplete?: (jobId: string) => void;
  onConversionFailed?: (jobId: string, error: string) => void;
}

// Supported file types and extensions
const SUPPORTED_FILE_TYPES = [
  'application/java-archive',
  'application/zip',
  'application/x-zip-compressed',
] as const;

const SUPPORTED_EXTENSIONS = ['.jar', '.zip'] as const;

const SUPPORTED_DOMAINS = [
  'curseforge.com',
  'www.curseforge.com',
  'modrinth.com',
  'www.modrinth.com',
] as const;

export const ConversionUploadEnhanced: React.FC<ConversionUploadProps> = ({
  onConversionStart,
  onConversionComplete,
  onConversionFailed,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [modUrl, setModUrl] = useState('');
  const [smartAssumptions, setSmartAssumptions] = useState(true);
  const [includeDependencies, setIncludeDependencies] = useState(true);
  const [isConverting, setIsConverting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentConversionId, setCurrentConversionId] = useState<string | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);

  // Progress tracking
  const [currentStatus, setCurrentStatus] = useState<ConversionStatus | null>(
    null
  );
  const [connectionStatus, setConnectionStatus] = useState<
    'connecting' | 'connected' | 'disconnected' | 'error'
  >('disconnected');

  // WebSocket and polling refs
  const wsRef = useRef<ReturnType<typeof createConversionWebSocket> | null>(
    null
  );
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null
  );
  const isMountedRef = useRef(true);

  const errorNotification = useErrorNotification();

  // File validation
  const validateFile = useCallback(
    (file: File): { isValid: boolean; error?: string } => {
      if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
        return {
          isValid: false,
          error: `File too large. Maximum size is ${MAX_FILE_SIZE_MB}MB.`,
        };
      }

      const hasValidType = SUPPORTED_FILE_TYPES.some(
        (type) => type === file.type
      );
      const hasValidExtension = SUPPORTED_EXTENSIONS.some((ext) =>
        file.name.toLowerCase().endsWith(ext)
      );

      const isValid = hasValidType || hasValidExtension;
      return {
        isValid,
        error: isValid
          ? undefined
          : 'Unsupported file type. Please upload .jar or .zip files only.',
      };
    },
    []
  );

  // URL validation
  const validateUrl = useCallback(
    (url: string): { isValid: boolean; error?: string } => {
      if (!url.trim()) {
        return { isValid: false, error: 'URL cannot be empty.' };
      }

      try {
        const urlObj = new URL(url);
        const isValid = SUPPORTED_DOMAINS.some(
          (domain) => urlObj.hostname === domain
        );
        return {
          isValid,
          error: isValid
            ? undefined
            : 'Please enter a valid CurseForge or Modrinth URL.',
        };
      } catch {
        return { isValid: false, error: 'Please enter a valid URL.' };
      }
    },
    []
  );

  // Cleanup function
  const cleanup = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.destroy();
      wsRef.current = null;
    }
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  // Reset conversion state
  const resetConversionState = useCallback(() => {
    cleanup();
    setSelectedFile(null);
    setModUrl('');
    setCurrentConversionId(null);
    setCurrentStatus(null);
    setUploadProgress(0);
    setIsConverting(false);
    setIsUploading(false);
    setError(null);
    setConnectionStatus('disconnected');
  }, [cleanup]);

  // Get status message
  const getStatusMessage = useCallback((): string => {
    if (isUploading) return `Uploading file... ${Math.round(uploadProgress)}%`;
    if (!currentStatus) return 'Ready to convert';

    const statusMessages: Record<string, string> = {
      [ConversionStatusEnum.PENDING]: 'Queued for processing...',
      [ConversionStatusEnum.UPLOADING]: 'Uploading file...',
      [ConversionStatusEnum.IN_PROGRESS]: 'Processing...',
      [ConversionStatusEnum.ANALYZING]: 'Analyzing mod structure...',
      [ConversionStatusEnum.CONVERTING]: 'Converting to Bedrock...',
      [ConversionStatusEnum.PACKAGING]: 'Packaging add-on...',
      [ConversionStatusEnum.COMPLETED]: 'Conversion completed!',
      [ConversionStatusEnum.FAILED]: 'Conversion failed',
      [ConversionStatusEnum.CANCELLED]: 'Conversion cancelled',
    };

    return (
      statusMessages[currentStatus.status] ||
      currentStatus.message ||
      'Processing...'
    );
  }, [currentStatus, isUploading, uploadProgress]);

  // Start polling as fallback
  const startPolling = useCallback(
    (jobId: string) => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }

      pollingIntervalRef.current = setInterval(async () => {
        if (!isMountedRef.current) return;

        try {
          const status = await getConversionStatus(jobId);
          console.log('[Polling] Status update:', status);
          setCurrentStatus(status);

          // Check for terminal states
          if (status.status === ConversionStatusEnum.COMPLETED) {
            cleanup();
            setIsConverting(false);
            if (onConversionComplete) {
              onConversionComplete(jobId);
            }
          } else if (status.status === ConversionStatusEnum.FAILED) {
            cleanup();
            setIsConverting(false);
            const errorMsg =
              status.error || status.message || 'Conversion failed';
            setError(errorMsg);
            if (onConversionFailed) {
              onConversionFailed(jobId, errorMsg);
            }
          } else if (status.status === ConversionStatusEnum.CANCELLED) {
            cleanup();
            setIsConverting(false);
          }
        } catch (error: any) {
          console.error('[Polling] Error:', error);
          if (!isMountedRef.current) return;
          setError(error.message || 'Failed to check conversion status');
        }
      }, 3000);
    },
    [cleanup, onConversionComplete, onConversionFailed]
  );

  // Setup WebSocket or polling for progress tracking
  const setupProgressTracking = useCallback(
    (jobId: string) => {
      // Try WebSocket first
      const ws = createConversionWebSocket(jobId);

      ws.onStatus((status) => {
        if (!isMountedRef.current) return;
        setConnectionStatus(status);
      });

      ws.onMessage((data) => {
        if (!isMountedRef.current) return;
        console.log('[WebSocket] Progress update:', data);
        setCurrentStatus(data);

        // Check for terminal states
        if (data.status === ConversionStatusEnum.COMPLETED) {
          cleanup();
          setIsConverting(false);
          if (onConversionComplete) {
            onConversionComplete(jobId);
          }
        } else if (data.status === ConversionStatusEnum.FAILED) {
          cleanup();
          setIsConverting(false);
          const errorMsg = data.error || data.message || 'Conversion failed';
          setError(errorMsg);
          if (onConversionFailed) {
            onConversionFailed(jobId, errorMsg);
          }
        } else if (data.status === ConversionStatusEnum.CANCELLED) {
          cleanup();
          setIsConverting(false);
        }
      });

      ws.connect();
      wsRef.current = ws;

      // Fallback polling after 5 seconds if WebSocket doesn't connect
      const pollingFallbackTimeout = setTimeout(() => {
        if (isMountedRef.current && connectionStatus !== 'connected') {
          console.log(
            '[Fallback] Starting polling due to WebSocket connection delay'
          );
          startPolling(jobId);
        }
      }, 5000);

      // Store timeout reference for cleanup
      return () => clearTimeout(pollingFallbackTimeout);
    },
    [
      connectionStatus,
      cleanup,
      onConversionComplete,
      onConversionFailed,
      startPolling,
    ]
  );

  // Handle file drop
  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: any[]) => {
      if (rejectedFiles.length > 0) {
        setError(
          'Unsupported file type. Please upload .jar or .zip files only.'
        );
        return;
      }

      const file = acceptedFiles[0];
      if (!file) return;

      const validation = validateFile(file);
      if (!validation.isValid) {
        setError(validation.error!);
        return;
      }

      setSelectedFile(file);
      setModUrl('');
      setError(null);

      if (currentConversionId) {
        resetConversionState();
      }
    },
    [currentConversionId, validateFile, resetConversionState]
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: {
      'application/java-archive': ['.jar'],
      'application/zip': ['.zip'],
      'application/x-zip-compressed': ['.zip'],
    },
    maxFiles: 1,
    multiple: false,
  });

  // Handle URL change
  const handleUrlChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const url = e.target.value;
      setModUrl(url);

      if (url) {
        setSelectedFile(null);
        if (currentConversionId) {
          resetConversionState();
        }
      }

      if (url) {
        const validation = validateUrl(url);
        setError(validation.isValid ? null : validation.error!);
      } else {
        setError(null);
      }
    },
    [currentConversionId, validateUrl, resetConversionState]
  );

  // Handle cancel
  const handleCancel = async () => {
    if (!currentConversionId) return;

    try {
      await cancelJob(currentConversionId);
      cleanup();
      setCurrentStatus((prev) =>
        prev ? { ...prev, status: ConversionStatusEnum.CANCELLED } : null
      );
      setIsConverting(false);
      setIsUploading(false);
    } catch (err: any) {
      setError(err.message || 'Failed to cancel conversion');
    }
  };

  // Handle download
  const handleDownload = async () => {
    if (!currentConversionId) return;

    try {
      await triggerDownload(currentConversionId);
    } catch (err: any) {
      setError(err.message || 'Failed to download conversion result');
    }
  };

  // Handle submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!selectedFile && !modUrl) {
      setError('Please select a file or enter a URL.');
      return;
    }

    if (modUrl) {
      const urlValidation = validateUrl(modUrl);
      if (!urlValidation.isValid) {
        setError(urlValidation.error!);
        return;
      }
    }

    setIsUploading(true);
    setIsConverting(true);
    setError(null);

    try {
      // Use real progress callback from API
      const request: InitiateConversionParams = {
        file: selectedFile || undefined,
        modUrl: modUrl || undefined,
        smartAssumptions,
        includeDependencies,
        onProgress: (progress) => {
          if (isMountedRef.current) {
            setUploadProgress(progress);
          }
        },
      };

      const response: ConversionResponse = await convertMod(request);

      setUploadProgress(100);
      setIsUploading(false);

      setCurrentConversionId(response.job_id);
      setCurrentStatus({
        job_id: response.job_id,
        status: ConversionStatusEnum.PENDING,
        progress: 0,
        message: response.message || 'Conversion started',
        created_at: new Date().toISOString(),
      });

      if (onConversionStart) {
        onConversionStart(
          response.job_id,
          selectedFile?.name || modUrl || 'unknown'
        );
      }

      // Setup progress tracking
      setupProgressTracking(response.job_id);
    } catch (err: any) {
      setIsUploading(false);
      setIsConverting(false);
      const errorMsg =
        err.message ||
        'Conversion request failed. Please check your connection and try again.';
      setError(errorMsg);
      errorNotification('Upload Failed', errorMsg);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      cleanup();
    };
  }, [cleanup]);

  const isProcessing = isConverting || isUploading;
  const isCompleted = currentStatus?.status === ConversionStatusEnum.COMPLETED;
  const isFailed = currentStatus?.status === ConversionStatusEnum.FAILED;
  const isCancelled = currentStatus?.status === ConversionStatusEnum.CANCELLED;
  const isFinished = isCompleted || isFailed || isCancelled;

  return (
    <div className="conversion-upload">
      <h2>Convert Your Modpack</h2>
      <p className="description">
        Upload your Java Edition modpack and we'll convert it to Bedrock Edition
        using smart assumptions.
      </p>

      {error && (
        <div className="error-message" role="alert" aria-live="polite">
          <span className="error-icon" aria-hidden="true">
            ⚠️
          </span>
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {/* File Upload Area */}
        <div
          {...getRootProps()}
          className={`dropzone ${isDragActive ? 'drag-active' : ''} ${selectedFile ? 'file-selected' : ''} ${isProcessing || isCompleted ? 'disabled-dropzone' : ''}`}
        >
          <input
            {...getInputProps()}
            aria-label="File upload"
            disabled={isProcessing || isCompleted}
          />

          {isFinished ? (
            <div className="upload-prompt">
              <div className="upload-icon">
                {isCompleted ? '🎉' : isFailed ? '❌' : '⏹️'}
              </div>
              <h3>{getStatusMessage()}</h3>
              <button
                type="button"
                className="browse-button"
                onClick={resetConversionState}
              >
                Start New Conversion
              </button>
            </div>
          ) : selectedFile ? (
            <div className="file-preview">
              <div className="file-icon">📦</div>
              <div className="file-info">
                <div className="file-name">{selectedFile.name}</div>
                <div className="file-size">
                  {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                </div>
                <div className="status">{getStatusMessage()}</div>
              </div>
              <button
                type="button"
                className="remove-file"
                onClick={(e) => {
                  e.stopPropagation();
                  if (!isProcessing && !isCompleted) setSelectedFile(null);
                }}
                disabled={isProcessing || isCompleted}
                aria-label={`Remove ${selectedFile.name}`}
              >
                <span aria-hidden="true">✕</span>
              </button>
            </div>
          ) : (
            <div className="upload-prompt initial-prompt">
              <div className="upload-icon-large">☁️</div>
              <h3>Drag & drop your modpack here</h3>
              <button
                type="button"
                className="browse-button"
                onClick={(e) => {
                  e.stopPropagation();
                  open();
                }}
                disabled={isProcessing || isCompleted}
              >
                Browse Files
              </button>
              <p className="supporting-text">
                Supports .jar files and .zip modpack archives
              </p>
            </div>
          )}
        </div>

        {/* URL Input Section */}
        {!selectedFile && !isFinished && (
          <div className="url-input-section">
            <div className="divider">
              <span>or paste URL</span>
            </div>
            <input
              type="url"
              aria-label="Modpack URL"
              value={modUrl}
              onChange={handleUrlChange}
              placeholder="https://www.curseforge.com/minecraft/mc-mods/your-mod or https://modrinth.com/mod/your-mod"
              className="url-input"
              disabled={!!selectedFile || isProcessing || isCompleted}
            />
            <div className="supported-sites">
              <span>Supported: CurseForge • Modrinth</span>
            </div>
          </div>
        )}

        {/* Configuration Options */}
        {!isFinished && (
          <ConversionOptions
            smartAssumptions={smartAssumptions}
            onSmartAssumptionsChange={setSmartAssumptions}
            includeDependencies={includeDependencies}
            onIncludeDependenciesChange={setIncludeDependencies}
            disabled={isProcessing || isCompleted}
          />
        )}

        {/* Action Buttons */}
        <div className="action-buttons">
          {!isFinished && (
            <>
              <button
                type="submit"
                className="convert-button"
                disabled={isProcessing || (!selectedFile && !modUrl)}
              >
                {isProcessing && (
                  <span
                    className="conversion-spinner"
                    aria-hidden="true"
                  ></span>
                )}
                {isUploading
                  ? `Uploading... ${Math.round(uploadProgress)}%`
                  : isProcessing
                    ? 'Processing...'
                    : 'Upload & Convert'}
              </button>

              {isProcessing && (
                <button
                  type="button"
                  className="cancel-button"
                  onClick={handleCancel}
                >
                  Cancel
                </button>
              )}
            </>
          )}

          {isCompleted && (
            <button
              type="button"
              className="download-button"
              onClick={handleDownload}
            >
              Download Converted Mod
            </button>
          )}
        </div>
      </form>
    </div>
  );
};

export default ConversionUploadEnhanced;
