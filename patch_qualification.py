"""
Add threshold_used parameter to log_qualification calls
"""

import re

# Read pipeline orchestrator
with open('backend/app/services/pipeline_orchestrator.py', 'r') as f:
    content = f.read()

# Pattern to find log_qualification calls without threshold_used
pattern1 = r'(self\.activity_logger\.log_qualification\([^)]*score=score,)\s*\n\s*(job_id=job_id)'
replacement1 = r'\1\n            threshold_used=icp.auto_approve_threshold,  # ✅ ADDED\n            \2'

pattern2 = r'(self\.activity_logger\.log_qualification\([^)]*score=score,)\s*\n\s*(job_id=job_id)'
replacement2 = r'\1\n            threshold_used=icp.review_threshold,  # ✅ ADDED\n            \2'

# Replace both occurrences
# First occurrence (auto_approved)
content = re.sub(
    r'decision="auto_approved",[^}]+score=score,\s*job_id=job_id',
    lambda m: m.group(0).replace('score=score,', 'score=score,\n            threshold_used=icp.auto_approve_threshold,'),
    content,
    count=1
)

# Second occurrence (pending_review)
content = re.sub(
    r'decision="pending_review",[^}]+score=score,\s*job_id=job_id',
    lambda m: m.group(0).replace('score=score,', 'score=score,\n            threshold_used=icp.review_threshold,'),
    content,
    count=1
)

# Write back
with open('backend/app/services/pipeline_orchestrator.py', 'w') as f:
    f.write(content)

print("✅ Added threshold_used parameters to log_qualification calls")
