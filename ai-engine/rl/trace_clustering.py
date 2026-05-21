import numpy as np
import logging
from typing import List, Dict, Any
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)

class TraceClustering:
    """
    Clusters reasoning traces to identify common successful patterns.
    """

    def __init__(self, n_clusters: int = 5):
        self.n_clusters = n_clusters
        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            max_features=1000,
            ngram_range=(1, 3)
        )
        self.model = KMeans(n_clusters=n_clusters, random_state=42)

    def cluster_traces(self, traces: List[str]) -> Dict[int, List[str]]:
        """
        Cluster a list of reasoning traces.
        """
        if not traces:
            return {}

        logger.info(f"Clustering {len(traces)} reasoning traces...")
        
        # Vectorize traces
        X = self.vectorizer.fit_transform(traces)
        
        # Fit model
        self.model.fit(X)
        labels = self.model.labels_
        
        # Group traces by cluster
        clusters = {i: [] for i in range(self.n_clusters)}
        for i, label in enumerate(labels):
            clusters[label].append(traces[i])
            
        return clusters

    def identify_expert_patterns(self, clusters: Dict[int, List[str]]) -> List[Dict[str, Any]]:
        """
        Identify common patterns in each cluster to propose new 'Expert' reasoning patterns.
        """
        expert_patterns = []
        
        feature_names = self.vectorizer.get_feature_names_out()
        
        for cluster_id, cluster_traces in clusters.items():
            if not cluster_traces:
                continue
                
            # Get top keywords for this cluster
            centroid = self.model.cluster_centers_[cluster_id]
            top_indices = centroid.argsort()[-5:][::-1]
            keywords = [feature_names[i] for i in top_indices]
            
            pattern = {
                "cluster_id": cluster_id,
                "keywords": keywords,
                "representative_trace": cluster_traces[0], # Simplification
                "frequency": len(cluster_traces)
            }
            expert_patterns.append(pattern)
            
        return expert_patterns

def create_trace_clusterer(n_clusters: int = 5) -> TraceClustering:
    return TraceClustering(n_clusters=n_clusters)
