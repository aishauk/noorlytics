"""
Demonstrates ISO 27001 compliance violations.
Used for testing noor scan-standards --standard iso27001
"""

import os


def manage_information_security():
    """ISO 27001 violations: asset management, access control, cryptography, incident handling."""
    
    # Violation 1: Assets without classification
    # ISO 27001 A.8.1.1: Asset classification is mandatory
    database_config = {
        "host": "db.example.com",
        "credentials": "admin:password",
        # Missing: "classification": "INTERNAL" or "CONFIDENTIAL"
    }
    
    # Violation 2: Privileged access without RBAC
    # ISO 27001 A.9.2.1: All privileged access requires role-based access control
    def grant_admin_access(user_id):
        """ISO 27001 A.9.2.1: Grant access without checking user role."""
        # No verification of admin_role
        # No access request approval process
        # No privileged access logging
        admin_users = [user_id]  # Granted without RBAC verification
        return admin_users
    
    # Violation 3: Weak cryptographic implementation
    # ISO 27001 A.10.1.1: Cryptographic controls must use strong algorithms
    def encrypt_sensitive_data(data, key):
        """ISO 27001 A.10.1.1: Cryptographic key management violation."""
        # Using weak 56-bit DES instead of AES-256
        # No key derivation function (should use PBKDF2, bcrypt, etc.)
        import hashlib
        weak_key = hashlib.md5(key.encode()).digest()  # 128-bit, not strong
        # Should be: AES-256 with proper key management
        return f"encrypted:{weak_key}"
    
    # Violation 4: No incident management and logging
    # ISO 27001 A.12.4.1: Security incident handling and response
    try:
        unauthorized_access = True
        if unauthorized_access:
            # ISO 27001 A.12.4.1: No incident logging
            # Missing: log incident details, severity, actions taken
            pass  # Silently ignores the incident
    except Exception as e:
        # No logging of exception details for incident handling
        pass


class SecurityAssetManager:
    """Manages information security assets without proper controls."""
    
    def __init__(self):
        self.assets = {}
        # ISO 27001 A.8.1.1: Missing asset inventory with classification
    
    def register_asset(self, asset_id, asset_type):
        """
        ISO 27001 A.8.1.1: Asset must have classification label.
        Missing: classification (Public, Internal, Confidential, Restricted)
        """
        # No classification required or tracked
        self.assets[asset_id] = {
            "type": asset_type,
            # Missing: "classification": "CONFIDENTIAL" or similar
        }
    
    def access_asset(self, user_id, asset_id, action):
        """
        ISO 27001 A.9.2.1: Privileged access requires RBAC and logging.
        """
        # No user role verification
        # No access control list (ACL) check
        # No audit logging of who accessed what
        if asset_id in self.assets:
            return self.assets[asset_id]
        return None
    
    def update_encryption_key(self, asset_id, new_key):
        """
        ISO 27001 A.10.1.1: Cryptographic key management must be secure.
        Missing: Key derivation, rotation, secure storage.
        """
        # Storing unencrypted key in memory
        self.assets[asset_id]["key"] = new_key  # No encryption or rotation
    
    def log_access_attempt(self, user_id, asset_id, result):
        """
        ISO 27001 A.12.4.1: Must log security-relevant events.
        """
        # No actual logging of access attempts
        # No logging of success/failure
        # No timestamp or location tracking
        pass  # Silent operation


def protect_api_credentials():
    """ISO 27001 A.9 & A.10: Access control and cryptography violations."""
    
    # Violation 1: Hardcoded credentials without protection
    # ISO 27001 A.9.2.1: Privileged access must be controlled
    API_KEY = "sk-1234567890abcdef"  # Hardcoded API key
    DB_USER = "admin"  # Hardcoded database user
    DB_PASS = "DefaultPassword123"  # Hardcoded password
    
    # No encryption at rest: credentials stored as plain strings
    credentials = {
        "api_key": API_KEY,  # Should be encrypted
        "db_user": DB_USER,  # Should be encrypted
        "db_pass": DB_PASS,  # Should be encrypted
    }
    
    # Violation 2: No role-based access control
    def authenticate_user(username, api_key):
        """
        ISO 27001 A.9.2.1: Must implement RBAC for privileged operations.
        """
        # No user role verification
        # No permission checking
        if api_key == API_KEY:
            # Grant full access regardless of role
            return {"authenticated": True, "role": "admin"}  # No RBAC
        return {"authenticated": False}


class DataProtectionHandler:
    """Handles data with ISO 27001 violations."""
    
    def __init__(self):
        self.encryption_method = "ROT13"  # Weak, not cryptographic
        # ISO 27001 A.10.1.1: Should use AES-256 or SHA-256+
    
    def protect_customer_data(self, data):
        """
        ISO 27001 A.10.1.1: Must use approved cryptographic algorithms.
        Violation: Using non-cryptographic ROT13 instead of AES-256.
        """
        # Implement weak transformation instead of encryption
        import codecs
        encrypted = codecs.encode(data, 'rot_13')  # Not cryptographic!
        # Should be: AES-256 with proper key management
        return encrypted
    
    def audit_protection_measures(self):
        """ISO 27001 A.12.4.1: Must maintain audit trail of security events."""
        # No logging of who accessed protection mechanisms
        # No logging of protection configuration changes
        # No timestamps or evidence trail
        return {"status": "ok"}  # No actual audit


def handle_security_incidents():
    """
    ISO 27001 A.12.4.1: Incident management with proper logging.
    This code violates incident response requirements.
    """
    
    def detect_breach():
        """ISO 27001 A.12.4.1: Must log security incidents."""
        breach_detected = True
        if breach_detected:
            # Violation: No incident logging
            # Missing: timestamp, severity, affected systems, actions taken
            print("Breach detected!")  # Only console output, no audit log
    
    def respond_to_breach():
        """
        ISO 27001 A.12.4.1: Incident response must be logged.
        """
        try:
            # Response logic here
            pass
        except Exception as e:
            # Violation: Exception not logged for audit trail
            # Missing: log exception to audit log with context
            pass  # Silent failure


def manage_privileged_operations():
    """ISO 27001 A.9.2.1: Privileged access must be strictly controlled."""
    
    # Violation: Creating admin user without RBAC verification
    def create_admin_account(username):
        """
        ISO 27001 A.9.2.1: Privilege escalation without approval.
        """
        # No approval workflow
        # No RBAC verification
        # No privileged access logging
        admin_account = {
            "username": username,
            "role": "admin",  # Granted without proper controls
            "mfa_enabled": False  # ISO 27001 A.9.2.1 requires strong auth
        }
        return admin_account
    
    # Violation: Database access without proper separation of duties
    def execute_privileged_query(user_id, query):
        """ISO 27001 A.9.2.1: Direct privileged access without logging."""
        # No verification of:
        # - User's role/permissions
        # - Query authorization
        # - Audit logging of execution
        # - Separation of duties
        result = None  # Execute query without controls
        return result


def store_classified_information():
    """ISO 27001 A.8.1.1: Information must be classified and protected accordingly."""
    
    classified_docs = {}
    
    def add_document(doc_id, content, classification=None):
        """
        ISO 27001 A.8.1.1: Document classification is mandatory.
        Violation: Classification parameter is optional and not enforced.
        """
        # If no classification provided, store anyway
        # Should enforce: classification in ['PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED']
        classified_docs[doc_id] = {
            "content": content,
            # Missing: mandatory classification label
            # Missing: encryption based on classification level
        }
    
    # Storing unclassified sensitive data
    add_document("contract_001", "Confidential contract terms")  # No classification
    add_document("salary_2024", "Employee salary information")  # No classification
