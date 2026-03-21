import os
import json
from groq import Groq


class GroqAIService:
    """Groq AI service for intelligent log analysis and remediation suggestions."""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.enabled = bool(self.api_key)

        # Preferred model order (can override first via GROQ_MODEL)
        preferred = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.model_candidates = [
            preferred,
            "llama-3.1-8b-instant",
        ]
        # Keep unique order
        self.model_candidates = list(dict.fromkeys(self.model_candidates))
        self.model = self.model_candidates[0]

        if self.enabled:
            self.client = Groq(api_key=self.api_key)
            print(f"Groq AI Service initialized (model: {self.model})")
        else:
            print("Warning: Groq AI disabled - no GROQ_API_KEY in .env")

    def _is_decommission_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "model_decommissioned" in msg
            or "decommissioned" in msg
            or "no longer supported" in msg
            or "invalid_request_error" in msg and "model" in msg
        )

    def _chat_completion(self, messages, temperature=0.7, max_tokens=300):
        last_error = None

        for candidate in self.model_candidates:
            try:
                response = self.client.chat.completions.create(
                    model=candidate,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if candidate != self.model:
                    self.model = candidate
                    print(f"Groq model switched to: {self.model}")
                return response
            except Exception as exc:
                last_error = exc
                if self._is_decommission_error(exc):
                    continue
                break

        raise last_error

    def analyze_anomaly(self, metric, value, threshold, recent_logs=None):
        """Analyze an anomaly and provide root cause + remediation steps."""
        if not self.enabled:
            return {
                "root_cause": "AI analysis unavailable (no API key)",
                "recommendations": ["Check system manually", "Review logs"],
            }

        try:
            prompt = f"""You are an AIOps expert analyzing a system anomaly.

ANOMALY DETECTED:
- Metric: {metric}
- Current Value: {value}
- Threshold: {threshold}
- Severity: CRITICAL

RECENT LOGS:
{recent_logs if recent_logs else "No logs provided"}

Please provide:
1. Root Cause Analysis (1-2 sentences)
2. Top 3 Recommended Actions (specific commands or steps)
3. Preventive Measures (how to avoid this in future)

Format as JSON:
{{
    "root_cause": "...",
    "recommendations": ["step 1", "step 2", "step 3"],
    "prevention": ["measure 1", "measure 2"]
}}
"""

            response = self._chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert Site Reliability Engineer analyzing production incidents.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )

            content = response.choices[0].message.content
            try:
                return json.loads(content)
            except Exception:
                return {
                    "root_cause": "Could not parse JSON from model response.",
                    "recommendations": [content],
                    "prevention": [],
                }

        except Exception as e:
            print(f"Groq AI error: {e}")
            return {
                "root_cause": f"Analysis failed: {str(e)}",
                "recommendations": ["Manual investigation required"],
                "prevention": [],
            }

    def chat(self, user_message, conversation_history=None):
        """Interactive chat with AIOps assistant."""
        if not self.enabled:
            return "AI assistant unavailable. Please add GROQ_API_KEY to .env file."

        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are an AIOps assistant helping DevOps engineers troubleshoot and fix production issues. Be concise and actionable.",
                }
            ]

            if conversation_history:
                messages.extend(conversation_history)

            messages.append({"role": "user", "content": user_message})

            response = self._chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=300,
            )
            return response.choices[0].message.content

        except Exception as e:
            return f"Error: {str(e)}"

    def generate_runbook(self, issue_type):
        """Generate a remediation runbook for common issues."""
        if not self.enabled:
            return "Runbook generation unavailable"

        try:
            prompt = f"""Generate a step-by-step remediation runbook for: {issue_type}

Include:
1. Immediate Actions (what to do right now)
2. Diagnostic Commands (how to gather more info)
3. Fix Steps (how to resolve)
4. Verification (how to confirm it's fixed)

Use shell commands where applicable. Be specific and actionable."""

            response = self._chat_completion(
                messages=[
                    {"role": "system", "content": "You are an SRE writing incident response runbooks."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=600,
            )
            return response.choices[0].message.content

        except Exception as e:
            return f"Error generating runbook: {str(e)}"


# Global instance
groq_service = GroqAIService()
