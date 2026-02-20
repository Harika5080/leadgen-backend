# test_pattern.py
import re

def extract_employee_count(text):
    """Test extraction"""
    text = text.strip()
    
    # Simple number at start
    simple_patterns = [
        r'^(\d{1,3}(?:,\d{3})+)',  # Start with comma number
        r'(\d{1,3}(?:,\d{3})+)\s*(?:\(|$|\+)',  # Number followed by ( or end
    ]
    
    for pattern in simple_patterns:
        match = re.search(pattern, text)
        if match:
            count_str = match.group(1).replace(',', '')
            count = int(count_str)
            if 10 <= count <= 10_000_000:
                return count
    return None

# Test cases
test_cases = [
    "8,100 (2024)",
    "10,000 employees",
    "11,000",
    "5,200+",
    "7,500 (2025)",
]

print("Testing extraction patterns:\n")
for test in test_cases:
    result = extract_employee_count(test)
    status = "✅" if result else "❌"
    print(f"{status} '{test}' -> {result}")