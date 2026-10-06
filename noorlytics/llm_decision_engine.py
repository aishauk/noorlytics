"""LLM Decision Engine - Generate context-aware decision rationales.

Enhances decisions with LLM-generated rationales based on customer context.
Supports multiple LLM backends with graceful fallback to static rationales.
"""

from __future__ import annotations

import logging
import hashlib
from typing import Optional, Dict, Any
from functools import lru_cache

from .assessment import Decision, CustomerContext
from .findings import FindingsCollection
from .llm_interface import LLMClient

logger = logging.getLogger(__name__)


class Rationale:
    """Container for decision rationale with metadata."""

    def __init__(self, text: str, source: str = "static", model: Optional[str] = None):
        """Initialize rationale.

        Args:
            text: Rationale text
            source: Source of rationale ("static" or "llm")
            model: LLM model used if source is "llm"
        """
        self.text = text
        self.source = source
        self.model = model

    def __str__(self) -> str:
        return self.text


class LLMDecisionEnhancer:
    """Enhances decisions with LLM-generated rationales."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model: str = "ollama:mistral",
        cache_size: int = 1000,
    ):
        """Initialize LLM decision enhancer.

        Args:
            llm_client: LLMClient instance
            model: Default LLM model to use
            cache_size: LRU cache size for rationales
        """
        self.llm_client = llm_client
        self.model = model
        self.cache_size = cache_size

    def enhance_decision(
        self,
        decision: Decision,
        customer_context: CustomerContext,
        findings: FindingsCollection,
        timeout: int = 5,
    ) -> Decision:
        """Generate LLM-based rationale for a decision.

        Args:
            decision: Decision to enhance
            customer_context: Customer context for personalization
            findings: Findings collection for evidence
            timeout: LLM request timeout in seconds

        Returns:
            Decision with enhanced rationale (or original if LLM fails)
        """
        if not self.llm_client:
            logger.debug(f"No LLM client configured, using static rationale for {decision.id}")
            decision.rationale_source = "static"
            return decision

        try:
            # Check cache
            rationale = self._get_cached_rationale(decision, customer_context, findings)
            if rationale:
                decision.rationale = rationale.text
                decision.rationale_source = rationale.source
                return decision

            # Generate new rationale via LLM
            prompt = self._build_prompt(decision, customer_context, findings)
            logger.debug(f"Generating LLM rationale for {decision.id} using {self.model}")

            if hasattr(self.llm_client, "chat"):
                rationale_text = self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=max(128, min(512, len(prompt.split()) * 2)),
                )
            else:
                rationale_text = self.llm_client.generate(
                    prompt,
                    model=self.model,
                    timeout=timeout,
                )

            if rationale_text:
                decision.rationale = rationale_text
                decision.rationale_source = "llm"
                logger.info(f"Generated LLM rationale for {decision.id}")
                return decision
            else:
                logger.warning(f"Empty response from LLM for {decision.id}, using static")
                decision.rationale_source = "static"
                return decision

        except TimeoutError:
            logger.warning(f"LLM timeout for {decision.id}, using static rationale")
            decision.rationale_source = "static"
            return decision
        except Exception as e:
            logger.error(f"LLM error for {decision.id}: {e}, using static rationale")
            decision.rationale_source = "static"
            return decision

    def enhance_batch(
        self,
        decisions: list[Decision],
        customer_context: CustomerContext,
        findings: FindingsCollection,
    ) -> list[Decision]:
        """Enhance multiple decisions with LLM rationales.

        Args:
            decisions: List of decisions to enhance
            customer_context: Customer context
            findings: Findings collection

        Returns:
            List of enhanced decisions
        """
        enhanced = []
        for decision in decisions:
            enhanced.append(self.enhance_decision(decision, customer_context, findings))
        return enhanced

    def _build_prompt(
        self,
        decision: Decision,
        customer_context: CustomerContext,
        findings: FindingsCollection,
    ) -> str:
        """Build a structured prompt for the LLM.

        Args:
            decision: Decision to explain
            customer_context: Customer context for personalization
            findings: Findings for evidence

        Returns:
            Formatted prompt for LLM
        """
        # Get relevant findings for evidence
        relevant_findings = [f for f in findings.findings if f.id in decision.evidence_ids]

        evidence_text = "\n".join([
            f"- {f.title} ({f.severity if hasattr(f, 'severity') else 'unknown'} severity)"
            for f in relevant_findings[:5]  # Limit to first 5 to avoid token limit
        ])

        prompt = f"""You are a security decision advisor for {customer_context.industry} organizations.

CUSTOMER PROFILE:
- Company: {customer_context.customer_name}
- Industry: {customer_context.industry}
- Deployment: {customer_context.deployment}
- Security Priority: {customer_context.risk_preferences.security.upper()}
- Business Continuity Priority: {customer_context.risk_preferences.business_continuity.upper()}
- Cost Control Priority: {customer_context.risk_preferences.cost_control.upper()}
- Delivery Speed Priority: {customer_context.risk_preferences.delivery_speed.upper()}

CONSTRAINTS:
- Upgrade Window: {customer_context.constraints.upgrade_window_days} days
- Requires OSS License Review: {"Yes" if customer_context.constraints.requires_oss_license_review else "No"}
- Legacy Runtime: {customer_context.constraints.legacy_runtime or "None"}

DECISION TO EXPLAIN:
Title: {decision.title}
Priority: {decision.priority.value}
Category: {decision.category.value}
Recommended Action: {decision.recommended_action}
Target Timeframe: {decision.target_timeframe}
Effort: {decision.effort_estimate}

EVIDENCE:
{evidence_text}

Please provide a concise, business-focused rationale (2-3 sentences) that:
1. Explains why this decision matters for {customer_context.customer_name}
2. References the {customer_context.industry} industry context
3. Respects their {customer_context.constraints.upgrade_window_days}-day upgrade window
4. Aligns with their {customer_context.risk_preferences.security} security priority

Rationale:"""

        return prompt

    def _get_cached_rationale(
        self,
        decision: Decision,
        customer_context: CustomerContext,
        findings: FindingsCollection,
    ) -> Optional[Rationale]:
        """Get cached rationale if available.

        Args:
            decision: Decision
            customer_context: Customer context
            findings: Findings

        Returns:
            Cached Rationale or None
        """
        # Create cache key from decision + context hash
        cache_key = self._make_cache_key(decision, customer_context)

        try:
            cached = self._rationale_cache(cache_key)
            if cached:
                logger.debug(f"Cache hit for {decision.id}")
                return cached
        except Exception as e:
            logger.debug(f"Cache lookup failed: {e}")

        return None

    @lru_cache(maxsize=1000)
    def _rationale_cache(self, cache_key: str) -> Optional[Rationale]:
        """LRU cache for rationales.

        Args:
            cache_key: Cache key

        Returns:
            Cached Rationale or None
        """
        # This is populated by enhance_decision when LLM generates a rationale
        return None

    def _make_cache_key(
        self,
        decision: Decision,
        customer_context: CustomerContext,
    ) -> str:
        """Create a cache key for a decision.

        Args:
            decision: Decision
            customer_context: Customer context

        Returns:
            Cache key string
        """
        # Hash of decision + customer context
        key_data = f"{decision.id}:{customer_context.customer_name}:{decision.category.value}"
        return hashlib.md5(key_data.encode()).hexdigest()


class LLMDecisionConfig:
    """Configuration for LLM decision enhancement."""

    def __init__(
        self,
        enabled: bool = True,
        model: str = "ollama:mistral",
        timeout: int = 5,
        fallback_to_static: bool = True,
    ):
        """Initialize configuration.

        Args:
            enabled: Whether to use LLM enhancement
            model: Default LLM model
            timeout: Request timeout
            fallback_to_static: Fall back to static rationales on LLM failure
        """
        self.enabled = enabled
        self.model = model
        self.timeout = timeout
        self.fallback_to_static = fallback_to_static

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> LLMDecisionConfig:
        """Create config from dictionary."""
        return LLMDecisionConfig(
            enabled=data.get("enabled", True),
            model=data.get("model", "ollama:mistral"),
            timeout=data.get("timeout", 5),
            fallback_to_static=data.get("fallback_to_static", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "model": self.model,
            "timeout": self.timeout,
            "fallback_to_static": self.fallback_to_static,
        }
