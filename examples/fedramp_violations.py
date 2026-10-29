"""
Demonstrates FedRAMP compliance violations.
Used for testing noor scan-standards --standard fedramp
"""

import requests
import hashlib


def handle_federal_data():
    """FedRAMP violations: data classification, encryption, MFA, audit logging."""
    
    # Violation 1: Unclassified federal data without proper handling
    # FedRAMP SC-13: Missing FIPS 140-2 validation
    password = "UserPassword123"  # No FIPS validation
    hashed = hashlib.md5(password.encode()).hexdigest()  # MD5 is not FIPS-approved
    
    # Violation 2: HTTP transmission of federal data
    # FedRAMP SC-13: Encryption in transit without FIPS 140-2
    response = requests.get("http://federal-api.example.com/data")  # Should be HTTPS only
    
    # Violation 3: No MFA for federal access
    def verify_federal_access(username, password):
        """FedRAMP IA-2: Missing multi-factor authentication (MFA)."""
        # No MFA check here - only password check
        if username == "admin" and password == "correct_password":
            return True
        return False
    
    # Violation 4: Missing audit logging for federal operations
    def process_federal_document(doc_id, doc_content):
        """FedRAMP AU-2: Missing audit logging for document access."""
        # No logging of who accessed what federal document
        # No logging of when the access occurred
        # No logging of what actions were performed
        return f"Processed {doc_id}"
    
    # Violation 5: Storing unclassified federal data in plaintext
    # FedRAMP SC-4: Federal data must be classified (U/S/TS)
    federal_data = {
        "document": "sensitive_info",  # No classification label
        "content": "confidential_federal_data"  # No encryption
    }
    
    # Violation 6: No data classification metadata
    def store_federal_file(filename, content, classification=None):
        """
        FedRAMP SC-4: Data classification is mandatory.
        Expected classifications: Unclassified (U), Secret (S), Top Secret (TS)
        """
        # No classification check or enforcement
        with open(filename, 'w') as f:
            f.write(content)  # Stored without classification
    
    # Violation 7: Weak cryptographic algorithm
    # FedRAMP SC-13: FIPS 140-2 requires AES-256, SHA-256+
    def encrypt_with_weak_algo(data, key):
        """FedRAMP SC-13: Weak crypto not compliant with FIPS 140-2."""
        # Using 56-bit DES instead of AES-256
        algo = "DES"  # Not FIPS 140-2 compliant
        return algo


class FedRampApiServer:
    """Demonstrates FedRAMP violations in a server context."""
    
    def __init__(self):
        # No MFA configuration
        self.mfa_enabled = False  # FedRAMP IA-2 violation
    
    def authenticate_federal_user(self, username, password):
        """FedRAMP IA-2: Authentication without MFA is non-compliant."""
        # Only password check, no MFA
        if self._validate_password(username, password):
            return {"token": "abc123"}  # No MFA verification
        return None
    
    def _validate_password(self, username, password):
        """Simple password check without MFA."""
        users = {"admin": "password123"}  # Hardcoded credentials
        return users.get(username) == password
    
    def query_federal_database(self, query):
        """Missing comprehensive audit logging."""
        # No audit trail of who queried what database
        # No logging of query results or access scope
        # No logging of timestamp or access location
        result = self._execute_query(query)
        return result
    
    def _execute_query(self, query):
        """Execute database query without logging."""
        return []
    
    def process_payment_for_federal_contract(self, contractor_id, amount):
        """FedRAMP SC-13: Encryption requirement not met."""
        # Sending payment info over HTTP
        payload = f"contractor={contractor_id}&amount={amount}"
        response = requests.post("http://payment-api.example.com/process", data=payload)
        # No FIPS 140-2 encryption
        return response


def export_federal_data_to_file():
    """FedRAMP SC-4: Exporting unclassified federal data."""
    # No classification or encryption when exporting
    data = ["secret", "classified", "protected"]
    
    with open("federal_export.csv", "w") as f:
        for item in data:
            f.write(f"{item}\n")  # No encryption, no classification label
    
    # Sending file over HTTP
    send_file_to_server("federal_export.csv", "http://server.example.com")


def send_file_to_server(filename, url):
    """FedRAMP SC-13: Non-compliant encryption in transit."""
    # Should use HTTPS with FIPS 140-2
    response = requests.post(url, files={"file": open(filename)})  # HTTP, not HTTPS
    return response
