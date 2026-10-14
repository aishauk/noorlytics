# Test file for security and compliance scanning

import json
import logging
import requests
from typing import Dict

logger = logging.getLogger(__name__)

# ===== SECURITY ISSUES =====

# 1. Hardcoded API key (secrets issue)
API_KEY = "sk-abc123def456ghi789"

# 2. HTTP with sensitive data (encryption issue)
def send_payment_data():
    url = "http://payment-api.example.com/charge"  # Should be HTTPS
    data = {"credit_card": "1234-5678-9012-3456", "amount": 100}
    response = requests.post(url, json=data)
    return response.json()

# 3. Logging sensitive data (secrets issue)
def process_user(user_email: str, ssn: str):
    logger.info(f"Processing user {user_email} with SSN {ssn}")  # SECURITY ISSUE
    # Process...
    return True

# 4. Storing credentials without encryption (encryption issue)
def save_credentials_to_file():
    creds = {
        "username": "admin",
        "password": "SecurePassword123!"
    }
    with open("credentials.json", "w") as f:
        json.dump(creds, f)  # SECURITY ISSUE - plaintext storage

# 5. Missing audit logging for sensitive operation (audit_logging issue)
def delete_user_account(user_id: int):
    # This is a sensitive operation - should have audit logging
    db.execute(f"DELETE FROM users WHERE id = {user_id}")
    # Missing: audit_log.record("delete_user", user_id=user_id)
    return True

# 6. Weak password validation (authentication issue)
def validate_password(password: str) -> bool:
    return len(password) >= 5  # SECURITY ISSUE - too weak!
