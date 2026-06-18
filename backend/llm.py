"""Model clients (B9).

Two providers live here, one per job:
  - Nebius Token Factory (research + guardrail). It is OpenAI-compatible, so we reach it with
    LangChain's ChatOpenAI pointed at the Nebius base_url.
  - Anthropic / Claude (the coding agent). We use the OFFICIAL `anthropic` SDK directly — not an
    OpenAI-compatible shim — because that is the supported, documented way to call Claude.

Keys + model ids come from .env (loaded here). Keeping every client in one small module means a
node asks for a model the same way and we only have one place to change when a provider moves.
"""

import os

import anthropic
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


def has_anthropic() -> bool:
    """True if an Anthropic key is configured — lets the coding node fall back gracefully."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def claude_model() -> str:
    """The Claude model id to use for the coding agent (override via ANTHROPIC_MODEL in .env)."""
    return os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")


def get_claude() -> anthropic.Anthropic:
    """The official Anthropic client. Reads ANTHROPIC_API_KEY; raises a clear error if it's unset."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return anthropic.Anthropic(api_key=api_key)
