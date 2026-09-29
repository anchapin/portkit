/**
 * ConfidenceBadge - Unified confidence score visualization
 * Canonical 0-1 → {label, color, aria} mapping shared across all components.
 * Part of Issue #1777 - Confidence Score Visualization Unification
 */

import React from 'react';

export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'unknown';

export interface ConfidenceConfig {
  level: ConfidenceLevel;
  label: string;
  color: string;
  bgColor: string;
  ariaLabel: string;
}

/**
 * Canonical threshold mapping for confidence scores.
 * All components must use these thresholds for consistency.
 */
export const CONFIDENCE_THRESHOLDS = {
  HIGH: 0.8,
  MEDIUM: 0.6,
} as const;

const getConfidenceConfig = (
  score: number | null | undefined
): ConfidenceConfig => {
  if (score === null || score === undefined) {
    return {
      level: 'unknown',
      label: 'Unknown',
      color: '#6c757d',
      bgColor: '#f8f9fa',
      ariaLabel: 'Confidence unknown',
    };
  }

  if (score >= CONFIDENCE_THRESHOLDS.HIGH) {
    return {
      level: 'high',
      label: 'High',
      color: '#28a745',
      bgColor: '#d4edda',
      ariaLabel: `High confidence: ${Math.round(score * 100)}%`,
    };
  }

  if (score >= CONFIDENCE_THRESHOLDS.MEDIUM) {
    return {
      level: 'medium',
      label: 'Medium',
      color: '#ffc107',
      bgColor: '#fff3cd',
      ariaLabel: `Medium confidence: ${Math.round(score * 100)}%`,
    };
  }

  return {
    level: 'low',
    label: 'Low',
    color: '#dc3545',
    bgColor: '#f8d7da',
    ariaLabel: `Low confidence: ${Math.round(score * 100)}%`,
  };
};

export interface ConfidenceBadgeProps {
  score: number | null | undefined;
  showPercentage?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/**
 * ConfidenceBadge - A unified badge component for displaying confidence scores.
 * Replaces: AssumptionsReport.ConfidenceIndicator, FeatureMapper confidence labels,
 * ComparisonView JSON dump, and AssumptionTracker emoji-based confidence.
 */
export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
  score,
  showPercentage = true,
  size = 'md',
  className = '',
}) => {
  const config = getConfidenceConfig(score);
  const percentage =
    score !== null && score !== undefined ? Math.round(score * 100) : null;

  const sizeStyles = {
    sm: { fontSize: '10px', padding: '2px 6px' },
    md: { fontSize: '12px', padding: '4px 8px' },
    lg: { fontSize: '14px', padding: '6px 12px' },
  };

  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        borderRadius: '9999px',
        fontWeight: 600,
        backgroundColor: config.bgColor,
        color: config.color,
        border: `1px solid ${config.color}40`,
        ...sizeStyles[size],
      }}
      title={config.ariaLabel}
      aria-label={config.ariaLabel}
    >
      <span
        style={{
          width: size === 'sm' ? '6px' : size === 'md' ? '8px' : '10px',
          height: size === 'sm' ? '6px' : size === 'md' ? '8px' : '10px',
          borderRadius: '50%',
          backgroundColor: config.color,
          flexShrink: 0,
        }}
        aria-hidden="true"
      />
      <span>{config.label}</span>
      {showPercentage && percentage !== null && (
        <span style={{ opacity: 0.8 }}>({percentage}%)</span>
      )}
    </span>
  );
};

export interface ConfidenceMeterProps {
  score: number | null | undefined;
  showLabel?: boolean;
  showPercentage?: boolean;
  height?: number;
  className?: string;
}

/**
 * ConfidenceMeter - A unified bar/meter component for displaying confidence scores.
 * Replaces: AssumptionsReport.ConfidenceIndicator bar visualization.
 */
export const ConfidenceMeter: React.FC<ConfidenceMeterProps> = ({
  score,
  showLabel = true,
  showPercentage = true,
  height = 8,
  className = '',
}) => {
  const config = getConfidenceConfig(score);
  const percentage =
    score !== null && score !== undefined ? Math.round(score * 100) : 0;

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
        width: '100%',
      }}
      role="progressbar"
      aria-valuenow={percentage}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={config.ariaLabel}
    >
      {(showLabel || showPercentage) && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '12px',
          }}
        >
          {showLabel && (
            <span style={{ color: config.color, fontWeight: 600 }}>
              {config.label} Confidence
            </span>
          )}
          {showPercentage && percentage > 0 && (
            <span style={{ color: '#6c757d' }}>{percentage}%</span>
          )}
        </div>
      )}
      <div
        style={{
          width: '100%',
          height: `${height}px`,
          backgroundColor: '#e9ecef',
          borderRadius: '4px',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${percentage}%`,
            height: '100%',
            backgroundColor: config.color,
            borderRadius: '4px',
            transition: 'width 0.3s ease-in-out',
          }}
        />
      </div>
    </div>
  );
};

/**
 * getConfidenceLevel - Utility function to get just the confidence level from a score.
 * Useful for conditional rendering based on confidence level.
 */
export const getConfidenceLevel = (
  score: number | null | undefined
): ConfidenceLevel => {
  return getConfidenceConfig(score).level;
};

/**
 * getConfidenceColor - Utility function to get the color for a confidence score.
 * Useful for inline styling in components that need custom rendering.
 */
export const getConfidenceColor = (
  score: number | null | undefined
): string => {
  return getConfidenceConfig(score).color;
};
