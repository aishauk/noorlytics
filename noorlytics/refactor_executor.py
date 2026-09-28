# noorlytics/refactor_executor.py
"""
Extract, validate, and apply refactoring changes from LLM-generated markdown plans.

Provides:
- ChangePriority: Enum for risk levels (HIGH, MEDIUM, LOW)
- RefactorChange: Data class for individual refactor steps
- RefactorPlanParser: Extract structured changes from markdown
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Set
from enum import Enum
import re
import keyword


class ChangePriority(Enum):
    """Risk/priority level of a refactor change."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def _is_code_truncated(code: str) -> bool:
    """Detect if code block is truncated or incomplete.
    
    Args:
        code: Code snippet to check
        
    Returns:
        True if code appears to be truncated (e.g., contains ... or ends abruptly)
    """
    # Check for ellipsis as placeholder, but ignore literal ellipses inside comments/docstrings.
    # The refactor plans often include comments like "# ... other functions" that should not
    # be treated as truncation.
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('#'):
            continue
        if stripped.startswith(('"""', "'''")) and stripped.endswith(('"""', "'''")):
            continue
        if stripped in {'...', '...}'}:
            return True
        if stripped.endswith('...') and not stripped.startswith('#'):
            return True
    
    # Check for unbalanced brackets/quotes
    if code.count('(') != code.count(')'):
        return True
    if code.count('[') != code.count(']'):
        return True
    if code.count('{') != code.count('}'):
        return True
    
    return False


@dataclass
class RefactorChange:
    """Represents a single refactoring change extracted from markdown plan."""
    priority: ChangePriority
    title: str
    problem_statement: str
    before_code: str  # Original code snippet
    after_code: str   # Refactored code snippet
    implementation_steps: List[str]  # Checklist items
    validation_instructions: str
    estimated_impact: Dict[str, str]  # {'readability': 'high', 'performance': 'low', ...}
    breakage_points: str
    depends_on: str = "None"  # Dependency description (e.g., "Change 1: Rename function")
    
    def is_safe(self) -> bool:
        """Determine if this change is safe to apply automatically.
        
        Only LOW priority changes are auto-applied without confirmation.
        """
        return self.priority == ChangePriority.LOW
    
    def is_complete(self) -> bool:
        """Check if before_code and after_code are complete (not truncated).
        
        Returns:
            True if both code blocks appear complete, False if either is truncated
        """
        return not (_is_code_truncated(self.before_code) or _is_code_truncated(self.after_code))

    @staticmethod
    def _extract_defined_symbol(code: str) -> tuple[str, str] | None:
        """Extract the first defined function or class name from a code block."""
        for line in code.splitlines():
            stripped = line.strip()
            func_match = re.match(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", stripped)
            if func_match:
                return "function", func_match.group(1)

            class_match = re.match(r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\(|:)", stripped)
            if class_match:
                return "class", class_match.group(1)

        return None

    @staticmethod
    def _extract_returned_name(code: str) -> str | None:
        """Extract a directly returned variable name when present."""
        match = re.search(r"^\s*return\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$", code, re.MULTILINE)
        return match.group(1) if match else None

    @staticmethod
    def _extract_assigned_names(code: str) -> list[str]:
        """Extract simple assigned variable names in source order."""
        return re.findall(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=", code, re.MULTILINE)

    @staticmethod
    def _extract_removed_variable(before_code: str, after_code: str) -> str | None:
        """Infer a variable removed by the refactor when possible."""
        before_assigned = RefactorChange._extract_assigned_names(before_code)
        after_assigned = set(RefactorChange._extract_assigned_names(after_code))
        returned_name = RefactorChange._extract_returned_name(before_code)

        for name in before_assigned:
            if name not in after_assigned and (returned_name is None or returned_name == name):
                return name

        return None

    @staticmethod
    def _extract_title_backticks(title: str) -> list[str]:
        """Extract backtick-delimited names from the refactor title."""
        return re.findall(r"`([^`]+)`", title)

    def detail_summary(self) -> str:
        """Return a concise, concrete description of what changed."""
        before_symbol = self._extract_defined_symbol(self.before_code)
        after_symbol = self._extract_defined_symbol(self.after_code)

        if before_symbol and after_symbol:
            before_kind, before_name = before_symbol
            after_kind, after_name = after_symbol

            if before_name != after_name:
                return f"{before_kind.title()}: `{before_name}` -> `{after_name}`"

            return f"{before_kind.title()}: `{before_name}`"

        return ""

    def display_note(self) -> str:
        """Return a short secondary note that clarifies scope or detected behavior."""
        before_symbol = self._extract_defined_symbol(self.before_code)
        after_symbol = self._extract_defined_symbol(self.after_code)
        removed_variable = self._extract_removed_variable(self.before_code, self.after_code)
        title_lower = self.title.lower()
        title_names = self._extract_title_backticks(self.title)

        normalized_before = re.sub(r"\s+", " ", self.before_code).strip()
        normalized_after = re.sub(r"\s+", " ", self.after_code).strip()

        if normalized_before == normalized_after:
            return "Detected change: no code difference in the provided before/after block"

        if before_symbol and after_symbol:
            before_kind, before_name = before_symbol
            _, after_name = after_symbol

            if before_name == after_name:
                if "rename" in title_lower:
                    return f"Detected change: {before_kind} name unchanged; body updated inside `{before_name}`"
                return f"Scope: {before_kind} `{before_name}`"

            return f"Scope: {before_kind} `{before_name}`"

        if removed_variable:
            return f"Detected change: removed assignment to `{removed_variable}`"

        if title_lower.startswith("rename variable") and len(title_names) >= 2:
            return f"Detected change: references updated from `{title_names[0]}` to `{title_names[1]}`"

        if title_lower.startswith("simplify"):
            return "Detected change: expression or control flow simplified"

        return ""

    def display_title(self) -> str:
        """Return a user-facing action summary for terminal output."""
        before_symbol = self._extract_defined_symbol(self.before_code)
        after_symbol = self._extract_defined_symbol(self.after_code)
        removed_variable = self._extract_removed_variable(self.before_code, self.after_code)
        title_lower = self.title.lower()
        title_names = self._extract_title_backticks(self.title)

        if title_lower.startswith("rename function") and len(title_names) >= 2:
            return f"Rename Function: `{title_names[0]}` -> `{title_names[1]}`"

        if title_lower.startswith("rename class") and len(title_names) >= 2:
            return f"Rename Class: `{title_names[0]}` -> `{title_names[1]}`"

        if title_lower.startswith("rename variable") and len(title_names) >= 2:
            if before_symbol:
                return f"Rename Variable: `{title_names[0]}` -> `{title_names[1]}` in `{before_symbol[1]}`"
            return f"Rename Variable: `{title_names[0]}` -> `{title_names[1]}`"

        if title_lower.startswith("remove unnecessary variable assignment"):
            if removed_variable and before_symbol:
                return f"Remove Unnecessary Variable: `{removed_variable}` from `{before_symbol[1]}`"
            if title_names and before_symbol:
                return f"Remove Unnecessary Variable in `{before_symbol[1]}`"

        if title_lower.startswith("simplify list comprehension") and before_symbol:
            return f"Simplify List Comprehension in `{before_symbol[1]}`"

        if title_lower.startswith("extract function") and len(title_names) >= 1:
            return f"Extract Function: `{title_names[0]}`"

        if title_lower.startswith("inline variable") and title_names:
            if before_symbol:
                return f"Inline Variable: `{title_names[0]}` in `{before_symbol[1]}`"
            return f"Inline Variable: `{title_names[0]}`"

        if before_symbol and after_symbol:
            before_kind, before_name = before_symbol
            _, after_name = after_symbol

            if "rename" in title_lower and before_name != after_name:
                return f"Rename {before_kind.title()}: `{before_name}` -> `{after_name}`"

            if "remove unnecessary variable" in title_lower and removed_variable:
                return f"Remove Unnecessary Variable: `{removed_variable}` from `{before_name}`"

            if "rename variable" in title_lower and removed_variable:
                return f"Rename Variable: `{removed_variable}` in `{before_name}`"

            if "rename" in title_lower:
                return f"Rename {before_kind.title()}: `{before_name}`"

            if "simplify" in title_lower:
                return f"Simplify {before_kind.title()}: `{before_name}`"

            if "remove unnecessary variable" in title_lower:
                return f"Remove Unnecessary Variable from `{before_name}`"

            return f"{self.title}: `{before_name}`"

        details = self.detail_summary()
        if details:
            return f"{self.title} [{details}]"
        return self.title


class RefactorPlanParser:
    """Parse markdown refactor plans and extract structured changes."""
    
    def __init__(self, markdown_plan: str):
        """Initialize parser with markdown content.
        
        Args:
            markdown_plan: Markdown text from LLM refactor response
        """
        self.markdown = markdown_plan
        self.changes: List[RefactorChange] = []
    
    def parse(self) -> List[RefactorChange]:
        """Extract refactor changes from markdown plan.
        
        Looks for blocks starting with [HIGH/MEDIUM/LOW] priority markers.
        Each block should contain:
        - Priority tag: [HIGH], [MEDIUM], or [LOW]
        - Title: First line after priority
        - Problem statement
        - Before code block (```language ... ```)
        - After code block (```language ... ```)
        - Implementation steps (- [ ] format)
        - Validation instructions
        - Estimated impact
        - Potential breakage points
        
        Returns:
            List of successfully parsed RefactorChange objects (sorted by priority: HIGH → MEDIUM → LOW)
        """
        # Split by priority markers to get blocks
        blocks = self._split_into_blocks()
        
        for block in blocks:
            change = self._extract_change_from_block(block)
            if change:
                self.changes.append(change)
        
        # Sort by priority: HIGH > MEDIUM > LOW
        priority_order = {ChangePriority.HIGH: 0, ChangePriority.MEDIUM: 1, ChangePriority.LOW: 2}
        self.changes.sort(key=lambda c: priority_order.get(c.priority, 3))
        
        # Auto-detect dependencies if not explicitly provided by LLM
        self._infer_implicit_dependencies()
        
        return self.changes
    
    def _split_into_blocks(self) -> List[str]:
        """Split markdown into blocks by priority markers or heuristics.
        
        First tries to find explicit [PRIORITY] markers.
        Falls back to detecting refactoring sections by heuristics (Before/After code blocks).
        """
        # Pattern: [HIGH/MEDIUM/LOW] at start of line, continue until next priority marker or end
        pattern = r"\n(\[(?:HIGH|MEDIUM|LOW)\].*?)(?=\n\[(?:HIGH|MEDIUM|LOW)\]|\Z)"
        blocks = re.findall(pattern, self.markdown, re.DOTALL)
        
        # Also check if the markdown starts with a priority marker (no leading newline)
        if not blocks and self.markdown.strip().startswith("["):
            pattern = r"(\[(?:HIGH|MEDIUM|LOW)\].*?)(?=\[(?:HIGH|MEDIUM|LOW)\]|\Z)"
            blocks = re.findall(pattern, self.markdown, re.DOTALL)
        
        # Fallback: detect sections with Before/After code blocks (even without priority markers)
        if not blocks:
            blocks = self._detect_fallback_blocks()
        
        return blocks
    
    def _detect_fallback_blocks(self) -> List[str]:
        """Detect refactoring blocks using heuristics when priority markers are missing.
        
        Looks for sections with:
        - A title/description
        - **Before:** or ```python ... ``` pattern indicating code
        - **After:** or another ```python ... ``` pattern
        
        Defaults to [LOW] priority for all fallback blocks.
        """
        blocks = []
        
        # Split by common section separators
        sections = re.split(r'\n---\n|\n##+ \[?(?:Refactoring|Suggestion|Change)', self.markdown)
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
            
            # Check if this section looks like a refactoring (has both before/after or multiple code blocks)
            has_before = bool(re.search(r'\*\*Before\*\*:?|Before:', section, re.IGNORECASE))
            has_after = bool(re.search(r'\*\*After\*\*:?|After:', section, re.IGNORECASE))
            code_blocks = len(re.findall(r'```(?:python)?', section))
            
            # If we have explicit Before/After markers or multiple code blocks, treat as refactoring section
            if (has_before and has_after) or code_blocks >= 2:
                # Extract title from first line if it looks like a title
                lines = section.split('\n')
                title = ""
                for i, line in enumerate(lines):
                    # Skip priority markers, we'll add them ourselves
                    if re.match(r'^\[(?:LOW|MEDIUM|HIGH)\]', line):
                        title = re.sub(r'^\[(?:LOW|MEDIUM|HIGH)\]\s*', '', line).strip()
                        break
                    elif line.strip() and not line.startswith('#') and not re.search(r'\*\*|```', line):
                        # First non-empty line that's not markdown
                        title = line.strip()
                        break
                    elif re.match(r'^#+\s+', line):
                        # Markdown header
                        title = re.sub(r'^#+\s+', '', line).strip()
                        break
                
                # If no title found, use first 50 chars
                if not title:
                    title = section[:50].replace('\n', ' ').strip()
                
                # Create block with [LOW] prefix so existing parser can handle it
                block = f"[LOW] {title}\n{section}"
                blocks.append(block)
        
        return blocks
    
    def _extract_change_from_block(self, block: str) -> Optional[RefactorChange]:
        """Extract a single change from a markdown block.
        
        Args:
            block: One refactor block starting with [PRIORITY]
            
        Returns:
            RefactorChange if successfully parsed, None otherwise
        """
        # Extract priority
        priority_match = re.match(r"\[(\w+)\]", block)
        if not priority_match:
            return None
        
        priority_str = priority_match.group(1)
        try:
            priority = ChangePriority[priority_str]
        except KeyError:
            return None
        
        # Extract title (everything after [PRIORITY] on first line)
        first_line_match = re.match(r"\[(\w+)\]\s+(.+?)(?:\n|$)", block)
        title = first_line_match.group(2) if first_line_match else ""
        
        if not title or title.startswith("Problem"):
            # Fallback: try to extract title from next non-empty line
            lines = block.split("\n")
            for i, line in enumerate(lines[1:], 1):
                if line.strip() and not line.strip().startswith(("Problem", "-", "*", "#", "[")):
                    title = line.strip()
                    break
        
        if not title:
            return None
        
        # Extract code blocks (all ```...``` sections)
        code_blocks = self._extract_code_blocks(block)
        
        if len(code_blocks) < 2:
            # Need at least before and after
            return None
        
        before_code = code_blocks[0].strip()
        after_code = code_blocks[1].strip()
        
        # Extract sections by markdown headers
        problem = self._extract_section(block, ["Problem", "Issue"])
        implementation = self._extract_checklist(block)
        validation = self._extract_section(block, ["Validation"])
        impact = self._extract_impact(block)
        breakage = self._extract_section(block, ["Breakage", "Edge cases"])
        depends_on = self._extract_section(block, ["Depends on", "Dependencies"]) or "None"
        
        return RefactorChange(
            priority=priority,
            title=title,
            problem_statement=problem,
            before_code=before_code,
            after_code=after_code,
            implementation_steps=implementation,
            validation_instructions=validation,
            estimated_impact=impact,
            breakage_points=breakage,
            depends_on=depends_on,
        )
    
    def _infer_implicit_dependencies(self) -> None:
        """Auto-detect implicit dependencies between changes based on code analysis.
        
        Analyzes all changes and identifies dependencies by:
        1. Detecting variable/function renames in one change and updates in another
        2. Detecting variable definitions and usages
        3. Detecting pattern matches between before_code of one change and after_code of another
        
        Updates depends_on field for changes that have implicit dependencies but didn't
        explicitly declare them (i.e., still have depends_on = "None").
        """
        if len(self.changes) <= 1:
            return  # No dependencies possible with only 0 or 1 change
        
        # Build mapping of what each change defines/modifies
        change_renames = {}  # Maps change idx to dict of {old_name: new_name}
        change_patterns = {}  # Maps change idx to set of identifiers used/defined
        
        for idx, change in enumerate(self.changes):
            # Extract variable and function names from before/after
            before_identifiers = self._extract_identifiers(change.before_code)
            after_identifiers = self._extract_identifiers(change.after_code)
            
            # Determine what was renamed or modified
            change_patterns[idx] = {
                'before': before_identifiers,
                'after': after_identifiers,
                'title': change.title.lower(),
                'problem': change.problem_statement.lower() if change.problem_statement else ""
            }
            
            # Look for renames: identifiers that changed
            renames = {}
            for old_name in before_identifiers:
                if old_name not in after_identifiers:
                    # This identifier was removed, look for its new name
                    for new_name in after_identifiers:
                        if new_name not in before_identifiers:
                            # Likely a rename
                            if self._is_likely_rename(old_name, new_name):
                                renames[old_name] = new_name
            
            if renames:
                change_renames[idx] = renames
        
        # Now detect dependencies: if change B uses/refers to something that change A renamed/modified
        for change_idx, change in enumerate(self.changes):
            # Check if this change has an explicit dependency (not the default "None" message)
            if not ("None" in change.depends_on and "independent" in change.depends_on):
                # Already has explicit dependency beyond the default
                continue
            
            # Check if this change depends on any previous change
            detected_deps = []
            
            for prev_idx in range(change_idx):
                prev_change = self.changes[prev_idx]
                dependency_reason = self._detect_dependency(
                    change_idx, prev_idx, 
                    change_renames.get(prev_idx, {}),
                    change_patterns
                )
                if dependency_reason:
                    detected_deps.append((prev_idx, prev_change.title, dependency_reason))
            
            # Update depends_on if we found implicit dependencies
            if detected_deps:
                # Use the most recent/direct dependency
                dep_idx, dep_title, reason = detected_deps[-1]
                change.depends_on = f"Change {dep_idx + 1} ({dep_title}): {reason}"
    
    def _extract_identifiers(self, code: str) -> Set[str]:
        """Extract variable and function names from code.
        
        Args:
            code: Python code snippet
            
        Returns:
            Set of identifiers (variable names, function names, etc.)
        """
        # Match Python identifiers: variable names, function names, parameters
        # Pattern matches: word characters that form valid Python identifiers
        pattern = r'\b([a-zA-Z_]\w*)\b'
        matches = re.findall(pattern, code)
        
        # Filter out Python keywords
        return {m for m in set(matches) if not keyword.iskeyword(m)}
    
    def _is_likely_rename(self, old_name: str, new_name: str) -> bool:
        """Determine if two names represent a likely rename operation.
        
        Examples:
        - 'process_data' -> 'process_items' (similar structure)
        - 'result' -> 'processed_items' (both are variable-like)
        - 'calc' -> 'calculate' (abbreviation expansion)
        
        Args:
            old_name: Original identifier
            new_name: New identifier
            
        Returns:
            True if this looks like a rename operation
        """
        if len(old_name) < 2 or len(new_name) < 2:
            return False
        
        # Check for similar structure (both variables, both functions, etc.)
        old_snake = old_name.lower().replace('_', '')
        new_snake = new_name.lower().replace('_', '')
        
        # If they share significant characters, likely a rename
        common_chars = len(set(old_snake) & set(new_snake))
        min_chars = min(len(old_snake), len(new_snake))
        
        return common_chars >= min_chars * 0.5  # At least 50% overlap
    
    def _detect_dependency(self, change_idx: int, prev_idx: int, 
                          prev_renames: Dict[str, str], 
                          patterns: Dict[int, Dict]) -> Optional[str]:
        """Detect if change_idx depends on prev_idx.
        
        Args:
            change_idx: Index of potential dependent change
            prev_idx: Index of potential prerequisite change
            prev_renames: Dict of renames made in prev_idx
            patterns: Dict mapping each change to its identifiers and metadata
            
        Returns:
            Reason string if dependency detected, None otherwise
        """
        curr_change = self.changes[change_idx]
        prev_change = self.changes[prev_idx]
        
        # Check 1: Exact rename match
        # If previous change renamed X to Y, and current change's before has X but after has Y
        # then current depends on previous
        for old_name, new_name in prev_renames.items():
            before_has_old = re.search(rf'\b{re.escape(old_name)}\b', curr_change.before_code)
            after_has_new = re.search(rf'\b{re.escape(new_name)}\b', curr_change.after_code)
            prev_after_has_new = re.search(rf'\b{re.escape(new_name)}\b', prev_change.after_code)
            
            if before_has_old and after_has_new and prev_after_has_new:
                return f"Updates references to '{old_name}' which was renamed to '{new_name}'"
        
        # Check 2: Pattern analysis - look at what changed in each file
        # If change A modifies identifier X -> Y and change B's before has X but after has Y
        # then B likely depends on A
        prev_before_ids = patterns[prev_idx]['before']
        prev_after_ids = patterns[prev_idx]['after']
        curr_before_ids = patterns[change_idx]['before']
        curr_after_ids = patterns[change_idx]['after']
        
        # Find what prev changed (identifiers removed and added)
        prev_removed = prev_before_ids - prev_after_ids
        prev_added = prev_after_ids - prev_before_ids
        
        # If current's before has something prev removed, and current's after has something prev added
        # this suggests dependency
        if prev_removed and prev_added:
            removed_in_curr = prev_removed & curr_before_ids
            added_in_curr = prev_added & curr_after_ids
            
            if removed_in_curr and added_in_curr:
                # Find one example to report
                removed_ex = removed_in_curr.pop()
                added_ex = added_in_curr.pop()
                return f"Updates references after refactoring ('{removed_ex}' -> '{added_ex}')"
        
        # Check 3: Title-based heuristics for common patterns
        prev_title_lower = prev_change.title.lower()
        curr_title_lower = curr_change.title.lower()
        
        # Common dependency patterns in titles
        if any(kw in prev_title_lower for kw in ['rename', 'refactor', 'replace', 'rename']):
            if any(kw in curr_title_lower for kw in ['update', 'fix', 'use', 'call']):
                # Extract identifiers from before/after to see if they match the pattern
                for name in prev_before_ids:
                    if name in curr_before_ids and \
                       name not in prev_after_ids and \
                       any(new_name in curr_after_ids for new_name in prev_added):
                        return f"Updates code after refactoring ('{name}')"
        
        return None
    
    def _extract_code_blocks(self, text: str) -> List[str]:
        """Extract all code blocks from text (```...``` sections).
        
        Args:
            text: Markdown text
            
        Returns:
            List of code block contents (without the ``` markers)
        """
        # Match: ``` optionally followed by language, then code, then ```
        pattern = r"```(?:\w+)?\s*\n(.*?)\n```"
        blocks = re.findall(pattern, text, re.DOTALL)
        return blocks
    
    def _extract_section(self, text: str, keywords: List[str]) -> str:
        """Extract text from a markdown section by keyword.
        
        Args:
            text: Markdown text
            keywords: List of possible section keywords (e.g., ["Problem", "Issue"])
            
        Returns:
            Extracted section text, empty string if not found
        """
        for keyword in keywords:
            # Pattern 1: Multi-line format (keyword followed by newline, then content)
            pattern = rf"(?:^|\n)(?:#+\s+)?{re.escape(keyword)}[:\s]*\n(.*?)(?=\n(?:#+\s+|\[)|\Z)"
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                # Clean up: remove leading/trailing whitespace and markdown formatting
                extracted = match.group(1).strip()
                # Remove leading markdown bullets/numbers if present
                extracted = re.sub(r"^[\s\*\-\d\.]+\s*", "", extracted)
                return extracted[:500]  # Limit to 500 chars for summaries
            
            # Pattern 2: Inline format (keyword on same line as content, e.g., "Depends on: value")
            pattern = rf"(?:^|\n)(?:#+\s+)?{re.escape(keyword)}:\s*([^\n]+)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()
                return extracted[:500]  # Limit to 500 chars for summaries
        
        return ""
    
    def _extract_checklist(self, text: str) -> List[str]:
        """Extract checklist items (- [ ] or - [x] format).
        
        Args:
            text: Markdown text
            
        Returns:
            List of checklist item texts
        """
        # Pattern: - [ ] or - [x] followed by text
        items = re.findall(r"^\s*-\s*\[[x ]\]\s+(.+)$", text, re.MULTILINE)
        return items[:5]  # Limit to 5 items
    
    def _extract_impact(self, text: str) -> Dict[str, str]:
        """Extract estimated impact metrics.
        
        Args:
            text: Markdown text
            
        Returns:
            Dict mapping metric names to impact levels (high/medium/low/none)
        """
        impact = {}
        metrics = ["readability", "performance", "maintainability", "security", "testability"]
        
        for metric in metrics:
            # Look for patterns like "readability (high)" or "readability: high"
            pattern = rf"{metric}\s*[:\(]*\s*(\w+)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                level = match.group(1).lower()
                if level in ("high", "medium", "low", "none", "unknown"):
                    impact[metric] = level
        
        return impact
    
    def get_change_summary(self) -> str:
        """Generate a text summary of all parsed changes.
        
        Returns:
            Human-readable summary string
        """
        if not self.changes:
            return "No refactoring changes found in plan."
        
        summary_parts = [f"Found {len(self.changes)} refactoring change(s):"]
        
        for i, change in enumerate(self.changes, 1):
            deps = f" (depends on: {change.depends_on})" if change.depends_on and change.depends_on.lower() != "none" else ""
            summary_parts.append(
                f"  [{i}] [{change.priority.value}] {change.title}{deps}"
            )
        
        return "\n".join(summary_parts)
    
    def to_markdown(self) -> str:
        """Regenerate markdown from parsed changes in priority-sorted order.
        
        Returns markdown with changes ordered HIGH → MEDIUM → LOW.
        This ensures the saved report prioritizes critical issues first.
        
        Returns:
            Formatted markdown string with all changes
        """
        if not self.changes:
            return "No refactoring suggestions found."
        
        markdown_parts = []
        
        for i, change in enumerate(self.changes, 1):
            priority_marker = f"[{change.priority.value}]"
            deps = f"Depends on: {change.depends_on}" if change.depends_on and change.depends_on.lower() != "none" else "Depends on: None (independent change)"
            
            # Build the markdown block
            block = f"""{priority_marker} {change.title}
Problem: {change.problem_statement}
{deps}

**Before:**
```python
{change.before_code}
```

**After:**
```python
{change.after_code}
```
"""
            markdown_parts.append(block)
        
        return "\n".join(markdown_parts)
    
    def validate_changes_against_file(self, file_content: str) -> dict:
        """Pre-flight validation: Check if changes can likely be applied.
        
        Analyzes each change to detect:
        - Code patterns that don't exist in the file
        - Undefined variables mentioned in suggestions
        - Dependency chains that might break
        
        Returns:
            Dict with 'appliance' (list of safe changes) and 'warnings' (issues)
        """
        import ast
        import re
        
        warnings = []
        safe_changes = []
        
        # Try to parse file for basic syntax errors
        try:
            ast.parse(file_content)
        except SyntaxError as e:
            warnings.append(f"File has syntax error at line {e.lineno}: {e.msg}")
        
        # Extract all variable names defined in the file
        defined_vars = set()
        for match in re.finditer(r'\b([a-z_][a-z0-9_]*)\s*=', file_content, re.IGNORECASE):
            defined_vars.add(match.group(1))
        
        # Check each change
        for i, change in enumerate(self.changes, 1):
            # Extract variables mentioned in before_code
            var_pattern = r'\b([a-z_][a-z0-9_]*)\b'
            vars_in_before = set(re.findall(var_pattern, change.before_code, re.IGNORECASE))
            
            # Check if before_code exists in file (exact or flexible)
            if change.before_code not in file_content:
                # Check if any variable in before_code is undefined
                undefined_in_before = vars_in_before - defined_vars
                if undefined_in_before:
                    warnings.append(
                        f"Change [{i}] '{change.title}': "
                        f"References undefined variable(s): {', '.join(undefined_in_before)}. "
                        f"This change might not apply correctly."
                    )
                else:
                    warnings.append(
                        f"Change [{i}] '{change.title}': "
                        f"Code pattern not found in file. "
                        f"This might be OK if code layout is different."
                    )
            else:
                safe_changes.append(change)
        
        return {
            'safe_changes': safe_changes,
            'warnings': warnings,
            'undefined_variables': defined_vars
        }


class DependencyGraph:
    """Build and analyze dependency relationships between changes.
    
    Handles:
    - Building dependency graph from RefactorChange objects
    - Finding all dependents of a change (transitive closure)
    - Grouping changes by dependency chains
    - Smart selection: when user selects a change, include all its dependents
    """
    
    def __init__(self, changes: List[RefactorChange]):
        """Initialize dependency graph.
        
        Args:
            changes: List of RefactorChange objects
        """
        self.changes = changes
        self.change_by_title = {ch.title: i for i, ch in enumerate(changes)}
        self.dependents_map = self._build_dependents_map()
    
    def _build_dependents_map(self) -> Dict[int, List[int]]:
        """Build a map of change index -> indices of changes that depend on it.
        
        Returns:
            Dict mapping change index to list of indices that depend on it
        """
        dependents = {i: [] for i in range(len(self.changes))}
        
        for i, change in enumerate(self.changes):
            if change.depends_on and change.depends_on.lower() != "none":
                # Find which change this depends on
                # The depends_on might be "Change 1: Rename function" or similar
                for j, other_change in enumerate(self.changes):
                    if j != i and other_change.title in change.depends_on:
                        dependents[j].append(i)
                        break
        
        return dependents
    
    def get_all_dependents(self, change_index: int, include_self: bool = True) -> List[int]:
        """Get all changes that depend on this change (transitively).
        
        Args:
            change_index: Index of the change
            include_self: Whether to include the change itself
            
        Returns:
            List of indices for all dependent changes (including transitive)
        """
        visited = set()
        stack = [change_index]
        
        while stack:
            idx = stack.pop()
            if idx in visited:
                continue
            visited.add(idx)
            stack.extend(self.dependents_map.get(idx, []))
        
        result = sorted(list(visited))
        if not include_self and change_index in result:
            result.remove(change_index)
        
        return result
    
    def get_chain_for(self, change_index: int) -> List[int]:
        """Get the complete dependency chain for a change (ancestors + self + descendants).
        
        Args:
            change_index: Index of the change
            
        Returns:
            Sorted list of all indices in the dependency chain
        """
        # Find ancestors (changes this depends on)
        ancestors = self._find_ancestors(change_index)
        
        # Find descendants (changes that depend on this)
        descendants = self.get_all_dependents(change_index, include_self=False)
        
        # Combine and sort
        chain = sorted(set(ancestors + [change_index] + descendants))
        return chain
    
    def _find_ancestors(self, change_index: int) -> List[int]:
        """Find all changes that this change depends on (transitively).
        
        Args:
            change_index: Index of the change
            
        Returns:
            List of ancestor indices
        """
        ancestors = []
        change = self.changes[change_index]
        
        if change.depends_on and change.depends_on.lower() != "none":
            # Find the change this directly depends on
            for j, other_change in enumerate(self.changes):
                if other_change.title in change.depends_on:
                    ancestors.append(j)
                    # Recursively find ancestors of that change
                    ancestors.extend(self._find_ancestors(j))
                    break
        
        return ancestors
    
    def group_by_chains(self) -> List[List[int]]:
        """Group changes by their dependency chains.
        
        Returns:
            List of dependency chains, where each chain is a list of indices
        """
        processed = set()
        chains = []
        
        for i in range(len(self.changes)):
            if i not in processed:
                chain = self.get_chain_for(i)
                chains.append(chain)
                processed.update(chain)
        
        # Sort chains by their first element
        chains.sort(key=lambda c: c[0])
        
        return chains
    
    def get_chain_summary(self, chain_indices: List[int]) -> str:
        """Get a visual summary of a dependency chain.
        
        Wraps chain across multiple lines if it exceeds terminal width.
        
        Args:
            chain_indices: List of change indices in the chain
            
        Returns:
            String showing chain structure with arrows, wrapped as needed
        """
        parts = []
        for idx in chain_indices:
            change = self.changes[idx]
            priority_emoji = "🔴" if change.priority == ChangePriority.HIGH else \
                            "🟡" if change.priority == ChangePriority.MEDIUM else "🟢"
            parts.append(f"{priority_emoji} {change.display_title()}")
        
        # Join with arrows and wrap to 90 chars per line
        full_chain = " → ".join(parts)
        
        # If chain fits on one line, return as-is
        if len(full_chain) <= 100:
            return full_chain
        
        # Otherwise, break into multiple lines
        lines = []
        current_line = ""
        
        for i, part in enumerate(parts):
            test_line = current_line + " → " + part if current_line else part
            
            # If adding this part would exceed line width, start new line
            if len(test_line) > 90 and current_line:
                lines.append(current_line)
                current_line = part
            else:
                current_line = test_line
        
        if current_line:
            lines.append(current_line)
        
        # Join lines with proper indentation
        return "\n   ".join(lines)
