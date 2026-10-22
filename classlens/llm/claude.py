"""One structured-output call to Claude, shared by every AI step (LLD §5.10).

Owns the client, the retry on an unreadable answer, refusals, user-facing error messages and the
failure log entries. Callers log their own "ok" entry with the stats this returns.
"""

import os
import time
from dataclasses import dataclass

import anthropic

from classlens import config
from classlens.runlog import RunLog, estimate_cost


def load_prompt(version: str) -> str:
    """A versioned system prompt, e.g. prompts/judge_v2.md."""
    return (config.PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")


class AIUnavailable(Exception):
    """An AI step could not run; the caller falls back to local-only mode. Message is user-facing."""


@dataclass
class CallStats:
    """Usage across the attempts of one call."""

    prompt_version: str
    effort: str
    model: str = config.MODEL
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    served_model: str | None = None  # differs from model if the server-side fallback answered
    stop_reason: str | None = None

    def add_response(self, response, seconds: float) -> None:
        self.latency_s += seconds
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        self.cost_usd += estimate_cost(response.usage)
        self.served_model = response.model
        self.stop_reason = response.stop_reason

    def as_dict(self) -> dict:
        return dict(vars(self))


class StructuredCall:
    """Sends a versioned system prompt plus one user message and parses the answer into a
    Pydantic model. Retries once if the answer is truncated or doesn't match the schema."""

    def __init__(self, purpose: str, prompt_version: str, effort: str, client=None, log: RunLog | None = None):
        self.purpose = purpose  # "judge", "roles": the log entry's purpose
        self.prompt_version = prompt_version
        self.effort = effort
        self.log = log or RunLog()
        self._client = client  # injected in tests; created from ANTHROPIC_API_KEY otherwise

    def run(self, user_text: str, output_format):
        """→ (parsed answer, CallStats). Raises AIUnavailable if no answer could be obtained."""
        client = self._get_client()
        system = load_prompt(self.prompt_version)
        stats = CallStats(self.prompt_version, self.effort)
        for _ in range(config.AI_MAX_ATTEMPTS):
            stats.attempts += 1
            started = time.monotonic()
            try:
                response = self._send(client, system, user_text, output_format)
            except ValueError:  # truncated or schema-invalid JSON
                stats.latency_s += time.monotonic() - started
                continue
            except anthropic.APIError as err:
                raise unavailable(err) from err

            stats.add_response(response, time.monotonic() - started)
            if response.stop_reason == "refusal":
                self.log.record(self.purpose, "refusal", stats.as_dict())
                raise AIUnavailable("The AI model declined to process this transcript.")
            if response.parsed_output is not None and response.stop_reason != "max_tokens":
                return response.parsed_output, stats

        self.log.record(self.purpose, "unreadable", stats.as_dict())
        raise AIUnavailable("The AI model's answer could not be read, even after a retry.")

    def _get_client(self):
        if self._client is None:
            if not os.environ.get(config.API_KEY_ENV):
                raise AIUnavailable("No Claude API key is configured, so the AI steps were skipped.")
            self._client = anthropic.Anthropic()
        return self._client

    def _send(self, client, system: str, user_text: str, output_format):
        return client.beta.messages.parse(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_text}],
            output_format=output_format,
            output_config={"effort": self.effort},
            betas=[config.FALLBACK_BETA],
            fallbacks="default",
        )


def unavailable(error: anthropic.APIError) -> AIUnavailable:
    """User-facing message for an SDK error (most specific type first)."""
    if isinstance(error, anthropic.AuthenticationError):
        return AIUnavailable("The Claude API key was rejected.")
    if isinstance(error, anthropic.RateLimitError):
        return AIUnavailable("The Claude API is rate-limited right now; try again shortly.")
    if isinstance(error, anthropic.APIStatusError):
        return AIUnavailable(f"The Claude API returned an error ({error.status_code}).")
    if isinstance(error, anthropic.APIConnectionError):
        return AIUnavailable("Could not reach the Claude API.")
    return AIUnavailable("The Claude API call failed.")
