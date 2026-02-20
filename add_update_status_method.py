# Find the line with "def get_bucket_display_name" and add update_status before it

with open('/app/app/models.py', 'r') as f:
    lines = f.readlines()

# Find the insertion point (before get_bucket_display_name)
insert_index = None
for i, line in enumerate(lines):
    if 'def get_bucket_display_name(self):' in line:
        insert_index = i
        break

if insert_index is None:
    # Try to find the end of LeadICPAssignment class (before next class or end)
    for i, line in enumerate(lines):
        if 'class LeadICPAssignment' in line:
            # Find the end of this class
            for j in range(i+1, len(lines)):
                if lines[j].startswith('class ') and 'LeadICPAssignment' not in lines[j]:
                    insert_index = j
                    break
            break

if insert_index:
    # Add the update_status method
    new_method = '''    def update_status(self, new_status: str):
        """Update assignment status and bucket"""
        self.status = new_status
        
        # Update bucket based on status
        status_to_bucket = {
            'new': 'new',
            'scored': 'score',
            'enriched': 'enriched',
            'verified': 'verified',
            'qualified': 'qualified',
            'pending_review': 'review',
            'rejected': 'rejected',
            'exported': 'exported'
        }
        
        if new_status in status_to_bucket:
            self.bucket = status_to_bucket[new_status]
    
'''
    
    # Insert the method
    lines.insert(insert_index, new_method)
    
    # Write back
    with open('/app/app/models.py', 'w') as f:
        f.writelines(lines)
    
    print("✅ Added update_status method to LeadICPAssignment")
else:
    print("❌ Could not find insertion point")
