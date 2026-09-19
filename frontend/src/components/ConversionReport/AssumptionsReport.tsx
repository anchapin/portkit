/**
 * AssumptionsReport Component - Enhanced smart assumptions reporting
 * Part of Issue #10 - Conversion Report Generation System
 */

import React, { useState, useMemo } from 'react';
import type {
  AssumptionsReport as AssumptionsReportType,
  AssumptionDetail,
} from '../../types/api';
import { ConfidenceMeter } from '../ui/confidence-badge';
import styles from './ConversionReport.module.css';

interface AssumptionsReportProps {
  assumptions: AssumptionsReportType;
  isExpanded: boolean;
  onToggle: () => void;
}

interface AssumptionCardProps {
  assumption: AssumptionDetail;
}

const ImpactBadge: React.FC<{ impact: string }> = ({ impact }) => {
  const getImpactInfo = (impact: string) => {
    const normalizedImpact = impact.toLowerCase();

    switch (normalizedImpact) {
      case 'high':
        return { color: '#dc3545', icon: '🔴', bg: '#f8d7da' };
      case 'medium':
        return { color: '#ffc107', icon: '🟡', bg: '#fff3cd' };
      case 'low':
        return { color: '#28a745', icon: '🟢', bg: '#d4edda' };
      default:
        return { color: '#6c757d', icon: '⚪', bg: '#f8f9fa' };
    }
  };

  const impactInfo = getImpactInfo(impact);

  return (
    <span
      className={styles.impactBadge}
      style={{
        backgroundColor: impactInfo.bg,
        color: impactInfo.color,
        border: `1px solid ${impactInfo.color}40`,
      }}
    >
      {impactInfo.icon} {impact}
    </span>
  );
};

const ConfidenceIndicator: React.FC<{ score: number }> = ({ score }) => {
  return (
    <ConfidenceMeter
      score={score}
      showLabel={false}
      showPercentage={true}
      height={6}
    />
  );
};

const AssumptionCard: React.FC<AssumptionCardProps> = ({ assumption }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className={styles.assumptionCard}>
      <div
        className={styles.assumptionHeader}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className={styles.assumptionTitle}>
          <h4 className={styles.assumptionFeature}>
            {assumption.feature_affected}
          </h4>
          <ImpactBadge impact={assumption.impact_level} />
        </div>
        <div className={styles.assumptionMetrics}>
          {assumption.confidence_score && (
            <ConfidenceIndicator score={assumption.confidence_score} />
          )}
          <button
            className={styles.expandButton}
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            {isExpanded ? '▼' : '▶'}
          </button>
        </div>
      </div>

      <div className={styles.assumptionPreview}>
        <p className={styles.userExplanation}>{assumption.user_explanation}</p>
      </div>

      {isExpanded && (
        <div className={styles.assumptionDetails}>
          <div className={styles.assumptionInfo}>
            <div className={styles.assumptionInfoItem}>
              <strong>Original Feature:</strong> {assumption.original_feature}
            </div>
            <div className={styles.assumptionInfoItem}>
              <strong>Bedrock Equivalent:</strong>{' '}
              {assumption.bedrock_equivalent}
            </div>
            <div className={styles.assumptionInfoItem}>
              <strong>Assumption Type:</strong> {assumption.assumption_type}
            </div>
            <div className={styles.assumptionInfoItem}>
              <strong>Description:</strong> {assumption.description}
            </div>
            <div className={styles.assumptionInfoItem}>
              <strong>Reasoning:</strong> {assumption.reasoning}
            </div>
          </div>

          {assumption.technical_details && (
            <div className={styles.technicalDetails}>
              <strong>Technical Details:</strong>
              <p className={styles.technicalText}>
                {assumption.technical_details}
              </p>
            </div>
          )}

          {assumption.alternatives_considered &&
            assumption.alternatives_considered.length > 0 && (
              <div className={styles.alternatives}>
                <strong>Alternatives Considered:</strong>
                <ul className={styles.alternativesList}>
                  {assumption.alternatives_considered.map(
                    (alternative, index) => (
                      <li key={index} className={styles.alternativeItem}>
                        {alternative}
                      </li>
                    )
                  )}
                </ul>
              </div>
            )}

          {assumption.visual_example && (
            <div className={styles.visualExample}>
              <strong>Visual Example:</strong>
              <div className={styles.exampleContainer}>
                {assumption.visual_example.before && (
                  <div className={styles.exampleItem}>
                    <h5>Before</h5>
                    <p>{assumption.visual_example.before}</p>
                  </div>
                )}
                {assumption.visual_example.after && (
                  <div className={styles.exampleItem}>
                    <h5>After</h5>
                    <p>{assumption.visual_example.after}</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const ImpactDistribution: React.FC<{
  distribution: Record<string, number>;
}> = ({ distribution }) => {
  const total = Object.values(distribution).reduce(
    (sum, count) => sum + count,
    0
  );

  if (total === 0) return null;

  return (
    <div className={styles.impactDistribution}>
      <h4>Impact Distribution</h4>
      <div className={styles.distributionChart}>
        {Object.entries(distribution).map(([level, count]) => {
          const percentage = (count / total) * 100;
          const getColor = (level: string) => {
            switch (level.toLowerCase()) {
              case 'high':
                return '#dc3545';
              case 'medium':
                return '#ffc107';
              case 'low':
                return '#28a745';
              default:
                return '#6c757d';
            }
          };

          return (
            <div key={level} className={styles.distributionItem}>
              <div className={styles.distributionLabel}>
                <span
                  className={styles.distributionColor}
                  style={{ backgroundColor: getColor(level) }}
                />
                {level} Impact
              </div>
              <div className={styles.distributionBar}>
                <div
                  className={styles.distributionFill}
                  style={{
                    width: `${percentage}%`,
                    backgroundColor: getColor(level),
                  }}
                />
              </div>
              <div className={styles.distributionCount}>
                {count} ({percentage.toFixed(0)}%)
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const CategoryBreakdown: React.FC<{
  categories: Record<string, AssumptionDetail[]>;
}> = ({ categories }) => {
  if (Object.keys(categories).length === 0) return null;

  return (
    <div className={styles.categoryBreakdown}>
      <h4>Assumptions by Category</h4>
      <div className={styles.categoriesGrid}>
        {Object.entries(categories).map(([category, assumptions]) => (
          <div key={category} className={styles.categoryCard}>
            <h5 className={styles.categoryTitle}>{category}</h5>
            <div className={styles.categoryCount}>
              {assumptions.length} assumptions
            </div>
            <div className={styles.categoryImpacts}>
              {assumptions.slice(0, 3).map((assumption, index) => (
                <ImpactBadge key={index} impact={assumption.impact_level} />
              ))}
              {assumptions.length > 3 && (
                <span className={styles.moreTag}>
                  +{assumptions.length - 3} more
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const FilterControls: React.FC<{
  onImpactFilter: (impact: string) => void;
  onCategoryFilter: (category: string) => void;
  impactFilter: string;
  categoryFilter: string;
  categories: string[];
}> = ({
  onImpactFilter,
  onCategoryFilter,
  impactFilter,
  categoryFilter,
  categories,
}) => {
  return (
    <div className={styles.filterControls}>
      <div className={styles.filterGroup}>
        <label>Impact Level:</label>
        <select
          value={impactFilter}
          onChange={(e) => onImpactFilter(e.target.value)}
        >
          <option value="all">All Impacts</option>
          <option value="high">High Impact</option>
          <option value="medium">Medium Impact</option>
          <option value="low">Low Impact</option>
        </select>
      </div>

      <div className={styles.filterGroup}>
        <label>Category:</label>
        <select
          value={categoryFilter}
          onChange={(e) => onCategoryFilter(e.target.value)}
        >
          <option value="all">All Categories</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
};

export const AssumptionsReport: React.FC<AssumptionsReportProps> = ({
  assumptions,
  isExpanded,
  onToggle,
}) => {
  const [impactFilter, setImpactFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');

  const categories = useMemo(() => {
    return Object.keys(assumptions.category_breakdown || {});
  }, [assumptions.category_breakdown]);

  const filteredAssumptions = useMemo(() => {
    const allAssumptions = assumptions.assumptions || [];
    if (impactFilter === 'all' && categoryFilter === 'all') {
      return allAssumptions;
    }

    // ⚡ Bolt: Single pass filter to avoid O(2N) complexity and intermediate array allocations
    return allAssumptions.filter((assumption) => {
      if (
        impactFilter !== 'all' &&
        assumption.impact_level?.toLowerCase() !== impactFilter
      ) {
        return false;
      }
      if (
        categoryFilter !== 'all' &&
        assumption.assumption_type !== categoryFilter
      ) {
        return false;
      }
      return true;
    });
  }, [assumptions.assumptions, impactFilter, categoryFilter]);

  const averageConfidence = useMemo(() => {
    if (!assumptions.assumptions || assumptions.assumptions.length === 0)
      return 0;
    const total = assumptions.assumptions.reduce(
      (sum, assumption) => sum + (assumption.confidence_score || 0.8),
      0
    );
    return total / assumptions.assumptions.length;
  }, [assumptions.assumptions]);

  if (!assumptions.assumptions || assumptions.assumptions.length === 0) {
    return (
      <div className={styles.section}>
        <div className={styles.sectionHeader} onClick={onToggle}>
          <h3 className={styles.sectionTitle}>
            🧠 Smart Assumptions (0 applied)
          </h3>
          <button
            className={styles.toggleButton}
            aria-expanded={isExpanded}
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            {isExpanded ? '▼' : '▶'}
          </button>
        </div>
        {isExpanded && (
          <div className={styles.sectionContent}>
            <p className={styles.noAssumptions}>
              No smart assumptions were required for this conversion. All
              features were directly translatable to Bedrock Edition.
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={styles.section}>
      <div className={styles.sectionHeader} onClick={onToggle}>
        <h3 className={styles.sectionTitle}>
          🧠 Smart Assumptions ({assumptions.total_assumptions_count} applied)
        </h3>
        <button
          className={styles.toggleButton}
          aria-expanded={isExpanded}
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          {isExpanded ? '▼' : '▶'}
        </button>
      </div>

      {isExpanded && (
        <div className={styles.sectionContent}>
          {/* Summary Information */}
          <div className={styles.assumptionsSummary}>
            <div className={styles.summaryCards}>
              <div className={styles.summaryCard}>
                <div className={styles.summaryValue}>
                  {assumptions.total_assumptions_count}
                </div>
                <div className={styles.summaryLabel}>Total Assumptions</div>
              </div>
              <div className={styles.summaryCard}>
                <div className={styles.summaryValue}>
                  {Math.round(averageConfidence * 100)}%
                </div>
                <div className={styles.summaryLabel}>Avg. Confidence</div>
              </div>
              <div className={styles.summaryCard}>
                <div className={styles.summaryValue}>{categories.length}</div>
                <div className={styles.summaryLabel}>Categories</div>
              </div>
            </div>

            <div className={styles.summaryDescription}>
              <p>
                Smart assumptions were applied to bridge compatibility gaps
                between Java and Bedrock editions. Each assumption maintains
                functionality while adapting to Bedrock's constraints.
              </p>
            </div>
          </div>

          {/* Impact Distribution */}
          {assumptions.impact_distribution && (
            <ImpactDistribution
              distribution={assumptions.impact_distribution}
            />
          )}

          {/* Category Breakdown */}
          {assumptions.category_breakdown &&
            Object.keys(assumptions.category_breakdown).length > 0 && (
              <CategoryBreakdown categories={assumptions.category_breakdown} />
            )}

          {/* Filter Controls */}
          <FilterControls
            onImpactFilter={setImpactFilter}
            onCategoryFilter={setCategoryFilter}
            impactFilter={impactFilter}
            categoryFilter={categoryFilter}
            categories={categories}
          />

          <div className={styles.resultsCount}>
            {filteredAssumptions.length} of{' '}
            {assumptions.total_assumptions_count} assumptions
          </div>

          {/* Assumptions List */}
          <div className={styles.assumptionsList}>
            {filteredAssumptions.map((assumption, index) => (
              <AssumptionCard
                key={assumption.assumption_id || index}
                assumption={assumption}
              />
            ))}
          </div>

          {filteredAssumptions.length === 0 && (
            <div className={styles.noResults}>
              <p>No assumptions match the current filters.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
