import React, { useState } from 'react';
import { ConfidenceBadge, ConfidenceMeter } from '../ui/confidence-badge';
import styles from './AssumptionTracker.module.css';

interface SmartAssumption {
  id: string;
  description: string;
  impact?: string;
  confidence?: string;
}

interface AssumptionTrackerProps {
  assumptions: SmartAssumption[];
}

const AssumptionTracker: React.FC<AssumptionTrackerProps> = ({
  assumptions,
}) => {
  const [expandedAssumption, setExpandedAssumption] = useState<string | null>(
    null
  );

  const getImpactIcon = (impact?: string) => {
    if (!impact) return '?';
    if (impact.toLowerCase().includes('high')) return '⚠️';
    if (impact.toLowerCase().includes('medium')) return '⚡';
    return '✅';
  };

  return (
    <div className={styles.container}>
      <h2 className={styles.title}>
        Smart Assumptions Applied ({assumptions.length})
      </h2>

      {assumptions.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>🎯</div>
          <p className={styles.emptyText}>
            No smart assumptions were needed for this conversion.
          </p>
          <p className={styles.emptySubtext}>
            This indicates a high-fidelity conversion with minimal compromises.
          </p>
        </div>
      ) : (
        <>
          <div className={styles.infoPanel}>
            <div className={styles.infoPanelHeader}>
              <span className={styles.infoPanelIcon}>💡</span>
              <strong className={styles.infoPanelTitle}>
                What are Smart Assumptions?
              </strong>
            </div>
            <p className={styles.infoPanelText}>
              Smart assumptions are intelligent decisions made during conversion
              when direct Java-to-Bedrock equivalents don't exist. They preserve
              the mod's core functionality while adapting to Bedrock's
              capabilities.
            </p>
          </div>

          <div className={styles.assumptionsGrid}>
            {assumptions.map((assumption) => (
              <div key={assumption.id} className={styles.assumptionCard}>
                <div
                  className={`${styles.assumptionHeader} ${
                    expandedAssumption === assumption.id
                      ? styles.assumptionHeaderExpanded
                      : styles.assumptionHeaderCollapsed
                  }`}
                  onClick={() =>
                    setExpandedAssumption(
                      expandedAssumption === assumption.id
                        ? null
                        : assumption.id
                    )
                  }
                >
                  <div className={styles.assumptionContent}>
                    <div className={styles.assumptionMain}>
                      <div className={styles.assumptionMeta}>
                        <span className={styles.assumptionId}>
                          {assumption.id}
                        </span>
                        {assumption.impact && (
                          <div className={styles.impactBadge}>
                            <span>{getImpactIcon(assumption.impact)}</span>
                            <span
                              className={`${styles.impactText} ${
                                assumption.impact.toLowerCase().includes('high')
                                  ? styles.impactHigh
                                  : assumption.impact
                                        .toLowerCase()
                                        .includes('medium')
                                    ? styles.impactMedium
                                    : assumption.impact
                                          .toLowerCase()
                                          .includes('low')
                                      ? styles.impactLow
                                      : styles.impactDefault
                              }`}
                            >
                              {assumption.impact.split(' - ')[0]} Impact
                            </span>
                          </div>
                        )}
                        {assumption.confidence && (
                          <div className={styles.confidenceBadge}>
                            <ConfidenceBadge
                              score={parseFloat(assumption.confidence)}
                              showPercentage={true}
                              size="sm"
                            />
                          </div>
                        )}
                      </div>
                      <p className={styles.assumptionDescription}>
                        {assumption.description}
                      </p>
                    </div>
                    <div
                      className={`${styles.expandIcon} ${
                        expandedAssumption === assumption.id
                          ? styles.expandIconExpanded
                          : styles.expandIconCollapsed
                      }`}
                    >
                      ▼
                    </div>
                  </div>
                </div>

                {expandedAssumption === assumption.id && (
                  <div className={styles.expandedContent}>
                    <h4 className={styles.expandedTitle}>
                      Detailed Impact Analysis
                    </h4>
                    <div className={styles.expandedDetails}>
                      {assumption.impact ? (
                        <div className={styles.impactDetail}>
                          <strong>Impact:</strong> {assumption.impact}
                        </div>
                      ) : null}

                      <div className={styles.whyNeeded}>
                        <strong>Why this assumption was needed:</strong>
                        <br />
                        This conversion choice was made because Bedrock Edition
                        has different capabilities and limitations compared to
                        Java Edition modding. The assumption ensures the mod's
                        core functionality is preserved while working within
                        Bedrock's constraints.
                      </div>

                      {assumption.confidence && (
                        <div className={styles.confidenceDetail}>
                          <strong>Confidence Level:</strong>
                          <div style={{ marginTop: '8px' }}>
                            <ConfidenceMeter
                              score={parseFloat(assumption.confidence)}
                              showLabel={true}
                              showPercentage={true}
                              height={6}
                            />
                          </div>
                          <span className={styles.confidenceSubtext}>
                            Higher confidence indicates more reliable conversion
                            accuracy.
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className={styles.proTip}>
            <div className={styles.proTipHeader}>
              <span className={styles.proTipIcon}>💡</span>
              <strong className={styles.proTipTitle}>Pro Tip</strong>
            </div>
            <p className={styles.proTipText}>
              Review these assumptions carefully to understand how your mod's
              behavior might differ in Bedrock Edition. Consider testing the
              converted add-on to ensure it meets your expectations.
            </p>
          </div>
        </>
      )}
    </div>
  );
};

export default AssumptionTracker;
