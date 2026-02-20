"""Generate bcrypt hashes for test users."""
import bcrypt

def hash_password(password: str) -> str:
    """Generate bcrypt hash."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')

# Generate hashes
admin_hash = hash_password("AdminPassword123!")
reviewer_hash = hash_password("ReviewerPass123!")
api_key_hash = hash_password("sk_live_test_key_12345")

print("=== Password Hashes ===")
print(f"\nAdmin Password: AdminPassword123!")
print(f"Hash: {admin_hash}")
print(f"\nReviewer Password: ReviewerPass123!")
print(f"Hash: {reviewer_hash}")
print(f"\nAPI Key: sk_live_test_key_12345")
print(f"Hash: {api_key_hash}")
