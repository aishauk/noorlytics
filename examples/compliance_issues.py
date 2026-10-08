# Test file for compliance standards scanning

import json
import logging
import requests

# ===== PCI-DSS ISSUES =====

def process_payment():
    # PCI-DSS Issue: Cardholder data in plaintext
    card_number = "4532-1234-5678-9999"
    ccv = "123"
    
    # PCI-DSS Issue: HTTP transmission for payment
    response = requests.post("http://payment-gateway.example.com/charge", 
                           json={"credit_card": card_number, "amount": 100})
    return response.json()

def log_transaction():
    # PCI-DSS Issue: Cardholder data in logs
    logging.info(f"Processing card: 4532123456789999")
    logging.debug(f"Card holder: John Doe")

# ===== HIPAA ISSUES =====

def store_patient_data():
    # HIPAA Issue: PHI transmitted over HTTP
    patient_ssn = "123-45-6789"
    patient_dob = "1990-01-15"
    
    requests.post("http://health-api.com/patient", 
                 json={"ssn": patient_ssn, "date_of_birth": patient_dob})

def save_medical_record():
    # HIPAA Issue: PHI storage without encryption
    medical_id = "MED12345"
    diagnosis = "Type 2 Diabetes"
    
    with open("medical_records.json", "w") as f:
        json.dump({
            "medical_id": medical_id,
            "diagnosis": diagnosis
        }, f)

# ===== SOC 2 ISSUES =====

def update_database_without_validation():
    # SOC 2 Issue: Data modification without validation
    database.update("SELECT * FROM users WHERE id = 1", {"role": "admin"})

def admin_operation_without_logging():
    # SOC 2 Issue: Admin operation without monitoring
    permission_level = "grant"
    user_id = "admin_001"
    # Missing audit logging here
