import requests
import openai
from noorlytics.config import COMPLIANCE_MODE, OPENAI_API_KEY
from noorlytics.llm_utils import count_tokens

OLLAMA_API_URL = "http://localhost:11434/api/generate"
openai.api_key = OPENAI_API_KEY


def suggest_refactorings(code_block, mode="dependencies", engine="ollama"):
    """
    Generate refactoring suggestions using Ollama or OpenAI.
    """
    prompt = (
        f"Analyze the following code from a {mode} perspective and provide concrete refactoring suggestions:\n\n"
        f"{code_block}"
    )

    if engine == "ollama":
        if not COMPLIANCE_MODE:
            raise EnvironmentError("Compliance mode must be enabled to use the local LLM.")

        response = requests.post(OLLAMA_API_URL, json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        })

        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            raise RuntimeError(f"LLM request failed: {response.status_code} - {response.text}")

    elif engine == "openai":
        model = "gpt-3.5-turbo"
        tokens_in = count_tokens(prompt, model)
        print(f"📏 Tokens in: {tokens_in}")

        completion = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return completion.choices[0].message.content

    else:
        raise ValueError("Invalid engine: choose 'ollama' or 'openai'")


def auto_refactor(code_block, mode="refactor"):
    """
    Placeholder for auto refactoring function using LLM.
    """
    print("⚙️  Auto refactoring not implemented yet.")
    return code_block


def generate_test_stubs(code_block, mode="tests", engine="ollama"):
    """
    Generate unit test stubs for the provided code using LLM.

    Args:
        code_block (str): The source code to analyze.
        engine (str): LLM engine ('ollama' or 'openai').

    Returns:
        str: Suggested unit test code as a string.
    """
    prompt = (
        f"Generate Python unit test stubs using unittest for the following code. "
        f"Only return the test code – no explanations or extra comments.\n\n"
        f"{code_block}"
    )

    if engine == "ollama":
        if not COMPLIANCE_MODE:
            raise EnvironmentError("Compliance mode must be enabled to use the local LLM.")

        response = requests.post(OLLAMA_API_URL, json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        })

        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            raise RuntimeError(f"Ollama test generation failed: {response.status_code} - {response.text}")

    elif engine == "openai":
        model = "gpt-3.5-turbo"
        tokens_in = count_tokens(prompt, model)
        print(f"📏 Tokens in: {tokens_in}")

        completion = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return completion.choices[0].message.content

    else:
        raise ValueError("Invalid engine: choose 'ollama' or 'openai'")