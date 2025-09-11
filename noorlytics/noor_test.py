import requests
import json

OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL = "codellama:7b-instruct"

code = """
def add(a, b): return a + b
"""

prompt = f"""You are a senior Python developer.
Suggest improvements to the following code.
Return 3 bullet points. Do not rewrite the code.

Code:
{code}
"""

response = requests.post(OLLAMA_API_URL, json={
    "model": MODEL,
    "prompt": prompt,
    "stream": False,
    "options": {"temperature": 0.3, "num_predict": 300}
}, timeout=60)

print("✅ Response:")
print(response.json()["response"])
