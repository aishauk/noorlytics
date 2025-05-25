import os
from dotenv import load_dotenv

load_dotenv()

COMPLIANCE_MODE = os.getenv("COMPLIANCE_MODE", "true").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")