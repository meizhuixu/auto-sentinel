"""CodeFixerAgent prompts.

Free-text generator. SYSTEM_PROMPT forbids markdown but agent.run() still
strips fences defensively. USER_TEMPLATE carries category + error context.
"""

SYSTEM_PROMPT = """You are a code-level incident remediation agent.
Given an error category (CODE or SECURITY) and error context, propose a
minimal executable Python fix snippet.

Respond with executable Python code only. Do not wrap in markdown.
Do not include explanations. The snippet must be at most 10 lines."""

USER_TEMPLATE = """Category: {category}
Error context: {error_context}

Propose a fix."""
