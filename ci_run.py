from openai import OpenAI
import tiktoken
from dotenv import load_dotenv
import os
import csv
from datetime import datetime

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def load_code(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def count_tokens(text, model="gpt-3.5-turbo"):
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))

def analyze_file(path):
    content = load_code(path)
    model = "gpt-3.5-turbo"
    mode = "analyze"

    prompt = f"""Analyze the code below for technical debt. Identify risks, outdated patterns, or poor structure.

Code:
```{content}```
"""

    tokens_in = count_tokens(prompt, model)
    input_cost = (tokens_in / 1000) * 0.0015

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    response_text = response.choices[0].message.content
    tokens_out = count_tokens(response_text, model)
    output_cost = (tokens_out / 1000) * 0.002
    total_cost = input_cost + output_cost

    # GitHub Actions loggvänligt format
    print(f"\n📂 File: {path}", flush=True)
    print(f"📏 In: {tokens_in} tokens | Out: {tokens_out} tokens", flush=True)
    print(f"💰 Total cost: ${total_cost:.4f}", flush=True)

    print("::group::🧠 GPT Summary", flush=True)
    for line in response_text.splitlines():
        print(line, flush=True)
    print("::endgroup::", flush=True)

    # Loggning till CSV
    log_file = "usage_log.csv"
    log_data = {
        "timestamp": datetime.now().isoformat(timespec='seconds'),
        "mode": mode,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total_tokens": tokens_in + tokens_out,
        "input_cost": round(input_cost, 4),
        "output_cost": round(output_cost, 4),
        "total_cost": round(total_cost, 4),
    }

    file_exists = os.path.isfile(log_file)
    with open(log_file, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=log_data.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(log_data)

if __name__ == "__main__":
    analyze_file("testfile.py")  # <- byt ut om du vill loopa flera