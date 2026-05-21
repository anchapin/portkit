import sqlite3
import json
import os
from collections import Counter

def audit_conversions(db_path):
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"Tables in database: {tables}")

    if 'conversion_examples' not in tables:
        print("Error: 'conversion_examples' table not found.")
        return

    # Fetch examples with quality scores
    cursor.execute("SELECT example_id, conversion_outcome, quality_score, detected_issues FROM conversion_examples WHERE quality_score < 0.7")
    failures = cursor.fetchall()

    print(f"\nFound {len(failures)} examples with quality_score < 0.7")

    # Analyze issues for failure reasons
    failure_reasons = []
    for fid, outcome, score, issues_json in failures:
        try:
            if issues_json:
                issues = json.loads(issues_json)
                for issue in issues:
                    reason = issue.get('type', 'unknown')
                    category = issue.get('category', 'general')
                    failure_reasons.append((category, reason))
            else:
                failure_reasons.append(('general', outcome or 'unknown'))
        except:
            failure_reasons.append(('error', 'parse_error'))

    counts = Counter(failure_reasons)
    print("\nTop Failure Categories/Reasons:")
    for (cat, res), count in counts.most_common(10):
        print(f"[{cat}] {res}: {count}")

    # Check for potential false failures (e.g., high quality manual rating but low score)
    cursor.execute("SELECT example_id, quality_score, user_rating FROM conversion_examples WHERE quality_score < 0.5 AND user_rating >= 4")
    potential_false_failures = cursor.fetchall()

    print(f"\nFound {len(potential_false_failures)} potential false failures (Low Score but High User Rating)")
    for fid, score, rating in potential_false_failures[:5]:
        print(f"ID: {fid}, Score: {score}, Rating: {rating}")

    conn.close()

if __name__ == "__main__":
    db_path = "ai-engine/training_data/conversion_examples.db"
    audit_conversions(db_path)
