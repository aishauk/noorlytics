try:
    import tiktoken
except ImportError:
    tiktoken = None

def count_tokens(text, model="gpt-3.5-turbo"):
    if tiktoken is None:
        raise RuntimeError(
            "Token counting requires OpenAI support. Install it with: python -m pip install 'noorlytics[openai]'"
        )
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))