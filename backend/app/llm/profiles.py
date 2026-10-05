"""Per-agent model preferences: an ordered list of models to try (primary first, then failover).

Groq models serve fast decision-heavy agents; Gemini serves long-context reading and writing.
Model IDs are config, not code: providers retire models, so keep these current.
"""

from app.llm.providers import ModelSpec

GROQ_REASONING = ModelSpec("groq", "openai/gpt-oss-120b")
GROQ_FAST = ModelSpec("groq", "llama-3.3-70b-versatile")
GEMINI_FLASH = ModelSpec("gemini", "gemini-3.5-flash")
GEMINI_FLASH_LITE = ModelSpec("gemini", "gemini-3.5-flash-lite")

AgentRole = str  # "planner" | "search" | "analysis" | "synthesis" | "writer"

DEFAULT_PROFILES: dict[AgentRole, list[ModelSpec]] = {
    "planner": [GROQ_REASONING, GEMINI_FLASH],
    "search": [GROQ_FAST, GEMINI_FLASH_LITE],
    "analysis": [GEMINI_FLASH, GROQ_REASONING],
    "synthesis": [GROQ_REASONING, GEMINI_FLASH],
    "writer": [GEMINI_FLASH, GROQ_REASONING],
}
