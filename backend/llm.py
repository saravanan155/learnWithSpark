"""Model clients (B7).

Nebius Token Factory is OpenAI-compatible, so we talk to it with LangChain's ChatOpenAI by
pointing it at the Nebius base_url. The key + model id come from .env (loaded here).

Keeping this in one small module means every node asks for a model the same way, and we only
have one place to change when we add Claude in B9.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()  # read backend/.env into environment variables


def has_nebius() -> bool:
    """True if a Nebius key is configured — lets nodes fall back gracefully when it isn't."""
    return bool(os.getenv("NEBIUS_API_KEY"))


def get_nebius(temperature: float = 0.7) -> ChatOpenAI:
    """A chat model backed by Nebius Token Factory."""
    api_key = os.getenv("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError("NEBIUS_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return ChatOpenAI(
        model=os.getenv("NEBIUS_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
        base_url=os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"),
        api_key=api_key,
        temperature=temperature,
    )
