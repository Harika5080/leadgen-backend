with open('/app/app/models.py', 'r') as f:
    content = f.read()

# Find LeadRejectionTracking class and add icp_id column
# Look for the line with lead_id and add icp_id after it

import re

# Pattern to find lead_id line in LeadRejectionTracking
pattern = r'(class LeadRejectionTracking.*?lead_id = Column\(UUID.*?\))'

match = re.search(pattern, content, re.DOTALL)

if match and 'icp_id = Column(UUID' not in content[match.end():match.end()+500]:
    # Find the position after lead_id line
    lead_id_match = re.search(
        r'(class LeadRejectionTracking.*?lead_id = Column\(UUID\(as_uuid=True\), ForeignKey\("leads\.id".*?\)[^\n]*\n)',
        content,
        re.DOTALL
    )
    
    if lead_id_match:
        # Insert icp_id right after lead_id
        insert_pos = lead_id_match.end()
        icp_id_line = '    icp_id = Column(UUID(as_uuid=True), ForeignKey("icps.id", ondelete="CASCADE"), nullable=True, index=True)\n'
        
        new_content = content[:insert_pos] + icp_id_line + content[insert_pos:]
        
        with open('/app/app/models.py', 'w') as f:
            f.write(new_content)
        
        print("✅ Added icp_id to LeadRejectionTracking model")
    else:
        print("❌ Could not find lead_id in LeadRejectionTracking")
else:
    print("✅ icp_id already exists in LeadRejectionTracking")
