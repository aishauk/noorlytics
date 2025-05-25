import os
import requests
import openai
from noorlytics.config import COMPLIANCE_MODE, OPENAI_API_KEY
from noorlytics.llm_utils import count_tokens

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_HEALTH_URL = "http://localhost:11434"

openai.api_key = OPENAI_API_KEY

def check_ollama_available():
    try:
        response = requests.get(OLLAMA_HEALTH_URL, timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False

def analyze_dependencies(content, filename="dependencies.txt", mode="ollama"):
    prompt = f"""
You are a senior dependency expert. Analyze the following file (`{filename}`) containing software dependencies (e.g., requirements.txt).

Tasks:
- Identify outdated, insecure, or unnecessary dependencies
- Recommend safe, modern version ranges that minimize risk of breaking changes
- Mention any critical updates or deprecations
- Assume this is a production application with tests in place

Respond with detailed suggestions and potential upgrade strategies.

File:
```plaintext
{content}
```
"""

    print(f"\n📦 Analyzing dependencies in {filename}")
    print(f"🔍 Mode: {mode}")

    if mode == "ollama":
        if not COMPLIANCE_MODE:
            raise EnvironmentError("Compliance mode must be enabled to use local LLM.")

        if not check_ollama_available():
            raise ConnectionError("❌ Ollama server is not reachable. Please run `ollama serve`.")

        response = requests.post(OLLAMA_API_URL, json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        })

        if response.status_code != 200:
            raise RuntimeError(f"Ollama request failed: {response.status_code} {response.text}")

        response_text = response.json().get("response", "")

    elif mode == "openai":
        model = "gpt-3.5-turbo"
        tokens_in = count_tokens(prompt, model)
        input_cost = (tokens_in / 1000) * 0.0015
        print(f"📏 Tokens in: {tokens_in} | 💵 Input cost: ${input_cost:.4f}")

        completion = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        response_text = completion.choices[0].message.content

        tokens_out = count_tokens(response_text, model)
        output_cost = (tokens_out / 1000) * 0.002
        total_cost = input_cost + output_cost

        print(f"📤 Tokens out: {tokens_out} | 💵 Output cost: ${output_cost:.4f}")
        print(f"💰 Total estimated cost: ${total_cost:.4f}\n")

    else:
        raise ValueError("Invalid mode: choose 'ollama' or 'openai'")

    # Save report
    output_dir = "reports"
    os.makedirs(output_dir, exist_ok=True)
    report_file = os.path.join(output_dir, f"{filename}_deps.md")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# Dependency Analysis Report for `{filename}`\n\n")
        f.write(response_text)

    print(f"📝 Dependency report saved to: {report_file}")
    return response_text
