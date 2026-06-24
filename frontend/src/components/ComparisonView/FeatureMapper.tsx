import React, { useState } from 'react';
import { ConfidenceBadge, getConfidenceColor } from '../ui/confidence-badge';

interface FeatureMappingData {
  id: string;
  java_feature: string;
  bedrock_equivalent: string;
  mapping_type: string;
  confidence_score: number | null;
}

interface FeatureMapperProps {
  features: FeatureMappingData[];
}

const FeatureMapper: React.FC<FeatureMapperProps> = ({ features }) => {
  const [selectedMapping, setSelectedMapping] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>('all');

  const filteredFeatures = features.filter((feature) => {
    if (filterType === 'all') return true;
    return feature.mapping_type === filterType;
  });

  // ⚡ Bolt optimization: Pre-calculate counts in a single O(N) pass
  // instead of calling .filter().length for every mapping type.
  const mappingTypeCounts = React.useMemo(() => {
    return features.reduce(
      (acc, feature) => {
        acc[feature.mapping_type] = (acc[feature.mapping_type] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>
    );
  }, [features]);

  const mappingTypes = Object.keys(mappingTypeCounts);

  return (
    <div
      style={{
        padding: '20px',
        border: '1px solid #e5e7eb',
        borderRadius: '8px',
        margin: '20px 0',
      }}
    >
      <h2 style={{ marginBottom: '20px', color: '#1f2937' }}>
        Feature Mappings ({features.length})
      </h2>

      {features.length === 0 ? (
        <p style={{ color: '#6b7280', fontStyle: 'italic' }}>
          No feature mappings available.
        </p>
      ) : (
        <>
          {/* Filter Controls */}
          <div style={{ marginBottom: '20px' }}>
            <label
              htmlFor="mapping-filter"
              style={{ marginRight: '10px', fontWeight: 'bold' }}
            >
              Filter by type:
            </label>
            <select
              id="mapping-filter"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              style={{
                padding: '5px 10px',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
              }}
            >
              <option value="all">All Types ({features.length})</option>
              {mappingTypes.map((type) => (
                <option key={type} value={type}>
                  {type} ({mappingTypeCounts[type]})
                </option>
              ))}
            </select>
          </div>

          {/* Feature Mapping Cards */}
          <div style={{ display: 'grid', gap: '15px' }}>
            {filteredFeatures.map((feature) => (
              <div
                key={feature.id}
                data-testid={`feature-card-${feature.id}`}
                style={{
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  padding: '15px',
                  backgroundColor:
                    selectedMapping === feature.id ? '#f3f4f6' : '#ffffff',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
                onClick={() =>
                  setSelectedMapping(
                    selectedMapping === feature.id ? null : feature.id
                  )
                }
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'start',
                    marginBottom: '10px',
                  }}
                >
                  <span
                    style={{
                      backgroundColor: '#e5e7eb',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      fontWeight: 'bold',
                    }}
                  >
                    {feature.mapping_type}
                  </span>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                    }}
                  >
                    <ConfidenceBadge
                      score={feature.confidence_score}
                      showPercentage={true}
                      size="sm"
                    />
                  </div>
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr auto 1fr',
                    gap: '10px',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontWeight: 'bold',
                        color: '#dc2626',
                        marginBottom: '5px',
                      }}
                    >
                      Java Feature
                    </div>
                    <div
                      style={{
                        backgroundColor: '#fef2f2',
                        padding: '8px',
                        borderRadius: '4px',
                        fontSize: '14px',
                      }}
                    >
                      {feature.java_feature || 'Unknown'}
                    </div>
                  </div>

                  <div
                    style={{
                      fontSize: '20px',
                      color: '#6b7280',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    →
                  </div>

                  <div>
                    <div
                      style={{
                        fontWeight: 'bold',
                        color: '#059669',
                        marginBottom: '5px',
                      }}
                    >
                      Bedrock Equivalent
                    </div>
                    <div
                      style={{
                        backgroundColor: '#f0fdf4',
                        padding: '8px',
                        borderRadius: '4px',
                        fontSize: '14px',
                      }}
                    >
                      {feature.bedrock_equivalent || 'Unknown'}
                    </div>
                  </div>
                </div>

                {selectedMapping === feature.id && (
                  <div
                    data-testid={`details-${feature.id}`}
                    style={{
                      marginTop: '15px',
                      padding: '10px',
                      backgroundColor: '#f9fafb',
                      borderRadius: '4px',
                    }}
                  >
                    <h4 style={{ margin: '0 0 8px 0', color: '#374151' }}>
                      Mapping Details
                    </h4>
                    <div style={{ fontSize: '14px', color: '#6b7280' }}>
                      <p>
                        <strong>ID:</strong> {feature.id}
                      </p>
                      <p>
                        <strong>Confidence Score:</strong>{' '}
                        {feature.confidence_score
                          ? `${(feature.confidence_score * 100).toFixed(1)}%`
                          : 'Not specified'}
                      </p>
                      <p>
                        <strong>Mapping Strategy:</strong>{' '}
                        {feature.mapping_type.replace(/_/g, ' ').toLowerCase()}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {filteredFeatures.length === 0 && (
            <p style={{ color: '#6b7280', fontStyle: 'italic' }}>
              No mappings match the selected filter.
            </p>
          )}
        </>
      )}
    </div>
  );
};

export default FeatureMapper;
