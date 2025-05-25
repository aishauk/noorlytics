import csv
from datetime import datetime
import os

from openai import OpenAI
import tiktoken
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def load_code(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def count_tokens(text, model="gpt-3.5-turbo"):
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))

def ask_gpt(content, mode="analyze"):
    model = "gpt-3.5-turbo"

    if mode == "refactor":
        prompt = f"""Refactor the code below to improve readability and reduce technical debt. Include rewritten code and a brief explanation.

Code:
```{content}```"""
    else:
        prompt = f"""Analyze the code below for technical debt. Identify risks, outdated patterns, or poor structure.

Code:
```{content}```"""

    tokens_in = count_tokens(prompt, model)
    input_cost = (tokens_in / 1000) * 0.0015
    print(f"\n📏 Tokens in: {tokens_in} | 💵 Input cost: ${input_cost:.4f}")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    response_text = response.choices[0].message.content

    if mode == "refactor":
        base_filename = os.path.basename(os.getenv("TARGET_FILE", "refactored"))
        name, ext = os.path.splitext(base_filename)
        output_file = f"{name}_refactored{ext}"
        with open(output_file, "w", encoding="utf-8") as f:
            if "```python" in response_text:
                code_block = response_text.split("```python")[1].split("```")[0].strip()
                f.write(code_block + "\n")
            else:
                f.write(response_text + "\n")
        print(f"💾 Refactored code saved to: {output_file}")

    output_dir = "reports"
    os.makedirs(output_dir, exist_ok=True)
    base_filename = os.path.basename(os.getenv("TARGET_FILE", "output"))
    name, _ = os.path.splitext(base_filename)
    report_file = os.path.join(output_dir, f"{name}_{mode}.md")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# {mode.capitalize()} report for `{base_filename}`\n\n")
        f.write(response_text)

    print(f"📝 Report saved to: {report_file}")

    tokens_out = count_tokens(response_text, model)
    output_cost = (tokens_out / 1000) * 0.002
    total_cost = input_cost + output_cost

    print(f"📤 Tokens out: {tokens_out} | 💵 Output cost: ${output_cost:.4f}")
    print(f"💰 Total estimated cost: ${total_cost:.4f}\n")

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

    return response_text


def analyze_dependencies(content, filename="dependencies.txt"):
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

    model = "gpt-3.5-turbo"
    tokens_in = count_tokens(prompt, model)
    input_cost = (tokens_in / 1000) * 0.0015
    print(f"\n📦 Analyzing dependencies in {filename}")
    print(f"📏 Tokens in: {tokens_in} | 💵 Input cost: ${input_cost:.4f}")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    response_text = response.choices[0].message.content

    output_dir = "reports"
    os.makedirs(output_dir, exist_ok=True)
    report_file = os.path.join(output_dir, f"{filename}_deps.md")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# Dependency Analysis Report for `{filename}`\n\n")
        f.write(response_text)

    print(f"📝 Dependency report saved to: {report_file}")

    tokens_out = count_tokens(response_text, model)
    output_cost = (tokens_out / 1000) * 0.002
    total_cost = input_cost + output_cost

    print(f"📤 Tokens out: {tokens_out} | 💵 Output cost: ${output_cost:.4f}")
    print(f"💰 Total estimated cost: ${total_cost:.4f}\n")

    return response_text


def analyze_requirements():
    req_file = "requirements.txt"
    if not os.path.exists(req_file):
        print("❌ requirements.txt not found.")
        return

    content = load_code(req_file)
    analyze_dependencies(content, filename=req_file)

def main():
    path = input("Set path to the file you want to analyze: ").strip()
    if not os.path.exists(path):
        print("File not found")
        return

    os.environ["TARGET_FILE"] = path
    filename = os.path.basename(path)

    mode = input("Choose mode: 'a' = analyze code, 'r' = refactor code, 'd' = analyze dependency file, 'req' = analyze requirements.txt: ").strip().lower()
    content = load_code(path)

    if mode == "d":
        result = analyze_dependencies(content, filename=filename)
    elif mode == "req":
        analyze_requirements()
        return
    else:
        result = ask_gpt(content, mode="refactor" if mode == 'r' else "analyze")

    print("\n--- Results ---\n")
    print(result)

if __name__ == "__main__":
    main()