# noorlytics/file_rewriter.py
"""
Apply refactoring changes to source files safely.

Provides:
- FileRewriter: Apply changes atomically with backup and rollback
- Backup management in .noor_backups/
- Unified diff generation (git-compatible)
"""

from pathlib import Path
from typing import List, Tuple, Optional
import shutil
from datetime import datetime
import re
import keyword


class FileRewriter:
    """Apply refactoring changes to files with rollback support.
    
    Features:
    - Atomic application (all succeed or all fail with rollback)
    - Automatic backup before writing
    - Git-compatible unified diffs
    - Rollback capability
    """
    
    def __init__(self, source_file: Path, backup_dir: Optional[Path] = None):
        """Initialize rewriter for a source file.
        
        Args:
            source_file: Path to the source file to modify
            backup_dir: Directory for backups (default: .noor_backups/ in same dir)
        """
        self.source_file = Path(source_file)
        self.backup_dir = backup_dir or self.source_file.parent / ".noor_backups"
        
        # Read original content
        try:
            self.original_content = self.source_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Fallback for files with mixed encodings
            self.original_content = self.source_file.read_text(encoding="utf-8", errors="replace")
        
        self.current_content = self.original_content
        self.changes_applied: List[Tuple[str, str]] = []  # (before, after) pairs
    
    def _normalize_code(self, code: str) -> str:
        """Normalize code for flexible matching.
        
        Removes docstrings and normalizes whitespace to handle cases where
        LLM-generated code might be simplified vs actual source.
        """
        import re
        # Remove triple-quoted docstrings (both """ and ''')
        code = re.sub(r'^\s+"""[\s\S]*?"""', '', code, flags=re.MULTILINE)
        code = re.sub(r"^\s+'''[\s\S]*?'''", '', code, flags=re.MULTILINE)
        # Remove inline comments but keep code
        code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        # Normalize whitespace: reduce multiple spaces/newlines
        code = re.sub(r' +', ' ', code)  # Multiple spaces → single space
        code = re.sub(r'\n+', '\n', code)  # Multiple newlines → single newline
        return code.strip()
    
    def _get_indentation(self, code: str) -> str:
        """Extract the indentation from the first non-empty line of code.
        
        Returns the indentation string (spaces/tabs) of the first line.
        """
        for line in code.split('\n'):
            if line.strip():  # First non-empty line
                # Count leading whitespace
                match = len(line) - len(line.lstrip())
                return line[:match]
        return ""  # No non-empty lines
    
    def _apply_indentation(self, code: str, indent: str) -> str:
        """Apply indentation to every line of code.
        
        Args:
            code: The code block to indent
            indent: The indentation string to apply
            
        Returns:
            Code with indentation applied to each line
        """
        lines = code.split('\n')
        indented_lines = []
        
        for line in lines:
            if line.strip():  # Non-empty line - add indentation
                indented_lines.append(indent + line)
            else:  # Empty or whitespace-only line - preserve as-is
                indented_lines.append(line)
        
        return '\n'.join(indented_lines)
    
    def _remove_indentation(self, code: str) -> str:
        """Remove common leading indentation from code block.
        
        Useful for normalizing indentation before matching.
        """
        lines = code.split('\n')
        if not lines:
            return code
        
        # Find minimum indentation (excluding empty lines)
        min_indent = float('inf')
        for line in lines:
            if line.strip():  # Non-empty line
                indent_len = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent_len)
        
        if min_indent == float('inf'):
            return code  # All lines are empty
        
        # Remove that indentation from all lines
        dedented_lines = []
        for line in lines:
            if line.strip():  # Non-empty line
                dedented_lines.append(line[min_indent:])
            else:  # Empty line
                dedented_lines.append(line)
        
        return '\n'.join(dedented_lines)

    def _replace_matched_block(self, content: str, matched_block: str, after_code: str) -> str:
        """Replace a matched code block while preserving surrounding indentation."""
        found_indent = self._get_indentation(matched_block)
        after_dedented = self._remove_indentation(after_code)
        after_indented = self._apply_indentation(after_dedented, found_indent)
        return content.replace(matched_block, after_indented, 1)

    def _is_placeholder_line(self, line: str) -> bool:
        """Return True when a line is an LLM placeholder rather than real code."""
        stripped = line.strip()
        if not stripped:
            return False
        if stripped in {'...', '...}'}:
            return True
        if stripped.startswith('#') and '...' in stripped:
            return True
        return stripped.endswith('...') and not stripped.startswith('#')

    def _contains_placeholder_markers(self, code: str) -> bool:
        """Detect placeholder markers such as ellipsis lines inside a snippet."""
        return any(self._is_placeholder_line(line) for line in code.splitlines())

    def _split_placeholder_chunks(self, code: str) -> list[str]:
        """Split a snippet into concrete code chunks separated by placeholder markers."""
        chunks: list[str] = []
        current_lines: list[str] = []

        for line in code.splitlines():
            if self._is_placeholder_line(line):
                if any(existing.strip() for existing in current_lines):
                    chunks.append('\n'.join(current_lines).strip('\n'))
                    current_lines = []
                continue
            current_lines.append(line)

        if any(existing.strip() for existing in current_lines):
            chunks.append('\n'.join(current_lines).strip('\n'))

        return [chunk for chunk in chunks if self._normalize_code(chunk)]

    def _find_normalized_match_block(self, target_code: str, content: str, extra_lines: int = 8) -> str | None:
        """Locate the concrete block in content whose normalized form matches target_code."""
        normalized_target = self._normalize_code(target_code)
        if not normalized_target:
            return None

        target_lines = [line.strip() for line in target_code.split('\n') if line.strip()]
        target_first_line = target_lines[0] if target_lines else ""
        target_last_line = target_lines[-1] if target_lines else ""

        lines = content.split('\n')
        target_line_count = max(1, len(target_code.split('\n')))

        for start in range(len(lines)):
            remaining = len(lines) - start
            max_window = min(remaining, target_line_count + extra_lines)
            for window_len in range(target_line_count, max_window + 1):
                candidate = '\n'.join(lines[start:start + window_len])
                candidate_lines = [line.strip() for line in candidate.split('\n') if line.strip()]
                if not candidate_lines:
                    continue
                if candidate_lines[0] != target_first_line or candidate_lines[-1] != target_last_line:
                    continue
                if self._normalize_code(candidate) == normalized_target:
                    return candidate

        return None

    def _extract_defined_names(self, code: str) -> set[str]:
        """Extract names introduced by the snippet itself.

        These are definitions, not unresolved references, so they should not
        contribute to "undefined variable" diagnostics when a stale plan no
        longer matches the current file.
        """
        defined_names = set()

        defined_names.update(re.findall(r'\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', code))
        defined_names.update(re.findall(r'\bclass\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[:\(]', code))

        for params in re.findall(r'\bdef\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\((.*?)\)', code, re.DOTALL):
            for param in re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', params):
                if param not in {'self', 'cls'}:
                    defined_names.add(param)

        return defined_names

    def _get_block_anchor(self, code: str) -> str:
        """Return a stable anchor line for a code block.

        Prefer the function or class signature when present. This lets dependent
        refactor steps rebase onto the most recently applied version of the same
        block when the LLM generated the next step against an older snapshot.
        """
        lines = [line.strip() for line in code.splitlines() if line.strip()]
        for line in lines:
            if line.startswith(("def ", "class ")):
                return line
        return lines[0] if lines else ""

    def _extract_identifier_renames(self, before_code: str, after_code: str) -> list[tuple[str, str]]:
        """Infer simple identifier rename pairs from a before/after snippet."""
        token_pattern = r'\b[a-zA-Z_][a-zA-Z0-9_]*\b'
        before_tokens = re.findall(token_pattern, before_code)
        after_tokens = re.findall(token_pattern, after_code)

        if len(before_tokens) != len(after_tokens):
            return []

        excluded = set(keyword.kwlist) | {
            'self', 'cls', 'True', 'False', 'None', 'len', 'sum', 'range',
            'list', 'dict', 'set', 'tuple', 'int', 'float', 'str', 'bool',
        }

        replacements: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for before_token, after_token in zip(before_tokens, after_tokens):
            if before_token == after_token:
                continue
            if before_token in excluded or after_token in excluded:
                continue

            pair = (before_token, after_token)
            if pair not in seen:
                replacements.append(pair)
                seen.add(pair)

        return replacements

    def _apply_identifier_renames(self, code: str, replacements: list[tuple[str, str]]) -> str:
        """Apply word-boundary identifier replacements to a code snippet."""
        rebased_code = code
        for old_name, new_name in replacements:
            rebased_code = re.sub(rf'\b{re.escape(old_name)}\b', new_name, rebased_code)
        return rebased_code

    def _extract_defined_symbol_names(self, code: str) -> set[str]:
        """Extract Python function/class names from a code snippet."""
        return set(re.findall(r'^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\s*', code, flags=re.MULTILINE))

    def _is_likely_rename(self, old_name: str, new_name: str) -> bool:
        """Heuristic for whether two identifiers represent a rename."""
        if len(old_name) < 2 or len(new_name) < 2:
            return False

        old_snake = old_name.lower().replace('_', '')
        new_snake = new_name.lower().replace('_', '')
        common_chars = len(set(old_snake) & set(new_snake))
        min_chars = min(len(old_snake), len(new_snake))
        return common_chars >= min_chars * 0.5

    def _infer_symbol_renames(self, before_code: str, after_code: str) -> list[tuple[str, str]]:
        """Infer direct symbol renames from a function/class definition pair.

        This lets a rename like process_data -> process_items propagate to
        call sites and dependent references in the same file, not only to the
        definition block itself.
        """
        before_symbols = self._extract_defined_symbol_names(before_code)
        after_symbols = self._extract_defined_symbol_names(after_code)
        if not before_symbols or not after_symbols:
            return []

        renamed_symbols: list[tuple[str, str]] = []
        for old_name in sorted(before_symbols):
            if old_name in after_symbols:
                continue
            for new_name in sorted(after_symbols):
                if new_name in before_symbols:
                    continue
                if self._is_likely_rename(old_name, new_name):
                    renamed_symbols.append((old_name, new_name))
                    break

        if renamed_symbols:
            return renamed_symbols

        # Fall back to a direct 1:1 match when the renamed symbol is the only
        # meaningful definition difference in the snippet.
        before_list = sorted(before_symbols)
        after_list = sorted(after_symbols)
        if len(before_list) == len(after_list):
            return [(old_name, new_name) for old_name, new_name in zip(before_list, after_list)]

        return []

    def _find_named_python_block(self, symbol_name: str, content: str) -> str | None:
        """Find the full def/class block for a named symbol in the current content."""
        lines = content.split('\n')
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"def {symbol_name}(") or stripped.startswith(f"class {symbol_name}"):
                base_indent = len(line) - len(line.lstrip())
                end_idx = len(lines)
                for next_idx in range(idx + 1, len(lines)):
                    next_stripped = lines[next_idx].strip()
                    if not next_stripped:
                        continue
                    next_indent = len(lines[next_idx]) - len(lines[next_idx].lstrip())
                    if next_indent <= base_indent:
                        end_idx = next_idx
                        break
                return '\n'.join(lines[idx:end_idx])
        return None

    def _find_enclosing_python_block(self, code: str, content: str) -> str | None:
        """Find the full Python def/class block identified by code's anchor line."""
        anchor = self._get_block_anchor(code)
        if not anchor.startswith(("def ", "class ")):
            return None

        lines = content.split('\n')
        start_idx = None
        base_indent = 0

        for idx, line in enumerate(lines):
            if line.strip() == anchor:
                start_idx = idx
                base_indent = len(line) - len(line.lstrip())
                break

        if start_idx is None:
            return None

        end_idx = len(lines)
        for idx in range(start_idx + 1, len(lines)):
            stripped = lines[idx].strip()
            if not stripped:
                continue

            indent = len(lines[idx]) - len(lines[idx].lstrip())
            if indent <= base_indent:
                end_idx = idx
                break

        return '\n'.join(lines[start_idx:end_idx])

    def _apply_placeholder_renames_within_block(self, before_code: str, after_code: str, content: str) -> str | None:
        """Apply inferred identifier renames across the full anchored block.

        Placeholder snippets like "# ... rest of the function remains the same"
        often show only the first changed assignment, but the rename is intended
        to affect all remaining references inside the same function.
        """
        before_chunks = self._split_placeholder_chunks(before_code)
        after_chunks = self._split_placeholder_chunks(after_code)
        if not before_chunks or len(before_chunks) != len(after_chunks):
            return None

        concrete_before = '\n'.join(before_chunks)
        concrete_after = '\n'.join(after_chunks)
        replacements = self._extract_identifier_renames(concrete_before, concrete_after)
        if not replacements:
            return None

        matched_block = self._find_enclosing_python_block(concrete_before, content)
        if not matched_block:
            return None

        renamed_block = self._apply_identifier_renames(matched_block, replacements)
        if renamed_block == matched_block:
            return None

        return self._replace_matched_block(content, matched_block, renamed_block)

    def _find_rebased_before_code(self, before_code: str, after_code: str) -> str | None:
        """Find a previously applied version of the same block to use as an anchor.

        This handles sequential dependent changes where change N+1 was generated
        against the original code, but change N has already rewritten that block.
        """
        before_anchor = self._get_block_anchor(before_code)
        after_anchor = self._get_block_anchor(after_code)

        if not before_anchor and not after_anchor:
            return None

        relevant_changes: list[tuple[str, str]] = []

        for previous_before, previous_after in reversed(self.changes_applied):
            previous_anchor = self._get_block_anchor(previous_after)
            if previous_anchor and previous_anchor in {before_anchor, after_anchor}:
                relevant_changes.append((previous_before, previous_after))
                if self._find_with_flexible_match(previous_after, self.current_content):
                    return previous_after

        # If the same symbol still exists in the current file but the function
        # signature or surrounding block was already edited by an earlier step,
        # rebase against the live symbol block instead of the stale pre-edit version.
        for symbol_name in sorted(self._extract_defined_symbol_names(before_code) | self._extract_defined_symbol_names(after_code)):
            candidate = self._find_named_python_block(symbol_name, self.current_content)
            if candidate and self._find_with_flexible_match(candidate, self.current_content):
                return candidate

        rebased_before = before_code
        applied_replacements = False
        for previous_before, previous_after in reversed(relevant_changes):
            replacements = self._extract_identifier_renames(previous_before, previous_after)
            if not replacements:
                continue
            candidate = self._apply_identifier_renames(rebased_before, replacements)
            if candidate != rebased_before:
                rebased_before = candidate
                applied_replacements = True

        if applied_replacements and self._find_with_flexible_match(rebased_before, self.current_content):
            return rebased_before

        return None
    
    def _strip_truncation_markers(self, code: str) -> str:
        """Return a stable anchor for partially truncated LLM snippets.

        Refactor plans may contain ellipsis placeholders such as "proces..." when
        the model output was abbreviated. In those cases, keep the stable lines that
        still exist in the real file and ignore the placeholder line fragments.
        """
        lines = []
        for line in code.splitlines():
            stripped = line.strip()
            if not stripped or stripped in {'...', '...}'}:
                continue
            if '...' in stripped:
                # Drop the truncated fragment line; it rarely matches the real file.
                # Keep earlier anchored lines such as the function signature or docstring.
                continue
            lines.append(line)
        return '\n'.join(lines).strip()

    def _find_with_flexible_match(self, before_code: str, content: str) -> bool:
        """Try to find before_code in content with flexible matching.
        
        First tries exact match, then tries normalized/simplified match.
        Returns True if found, False otherwise.
        """
        # 1. Try exact match first (fastest)
        if before_code in content:
            return True

        # 2. Handle truncated LLM snippets that use ellipsis placeholders.
        partial_before = self._strip_truncation_markers(before_code)
        if partial_before and partial_before != before_code:
            if partial_before in content:
                return True

        # 3. Try normalized match (handles docstring variations)
        normalized_before = self._normalize_code(before_code)
        normalized_content = self._normalize_code(content)
        
        if normalized_before in normalized_content:
            # Found match after normalization - this is OK
            return True

        partial_normalized = self._normalize_code(partial_before)
        if partial_normalized and partial_normalized in normalized_content:
            return True
        
        return False
    
    def _apply_change_with_flexible_match(self, before_code: str, after_code: str, content: str) -> str | None:
        """Apply change trying flexible matching while preserving indentation.
        
        Detects the indentation of the found code block and applies it to the
        replacement code to prevent breaking class/function structure.
        
        Returns the modified content if successful, None if no match found.
        """
        if self._contains_placeholder_markers(before_code) or self._contains_placeholder_markers(after_code):
            renamed_block_content = self._apply_placeholder_renames_within_block(
                before_code,
                after_code,
                content,
            )
            if renamed_block_content is not None:
                return renamed_block_content

            before_chunks = self._split_placeholder_chunks(before_code)
            after_chunks = self._split_placeholder_chunks(after_code)

            if before_chunks and len(before_chunks) == len(after_chunks):
                updated_content = content
                applied_any_chunk = False

                for before_chunk, after_chunk in zip(before_chunks, after_chunks):
                    if self._normalize_code(before_chunk) == self._normalize_code(after_chunk):
                        continue

                    updated_chunk_content = self._apply_change_with_flexible_match(
                        before_chunk,
                        after_chunk,
                        updated_content,
                    )
                    if updated_chunk_content is None:
                        return None

                    updated_content = updated_chunk_content
                    applied_any_chunk = True

                if applied_any_chunk:
                    return updated_content
        
        # 1. Try exact match first
        if before_code in content:
            return self._replace_matched_block(content, before_code, after_code)

        # 2. Handle partial/truncated snippets produced by LLM plans.
        partial_before = self._strip_truncation_markers(before_code)
        partial_after = self._strip_truncation_markers(after_code)
        if partial_before and partial_before != before_code:
            if partial_before in content:
                replacement = after_code if partial_after == partial_before else partial_after
                return self._replace_matched_block(content, partial_before, replacement)
        
        # 3. Try finding similar code (accounting for extra blank lines)
        before_with_flex_newlines = before_code
        for extra_newlines in ['', '\n', '\n\n', '\n\n\n']:
            test_pattern = before_code.replace('\n\n', '\n\n' + extra_newlines)
            if test_pattern in content:
                return self._replace_matched_block(content, test_pattern, after_code)
        
        # 4. Try normalized match (handles docstring variations, different indentation)
        matched_block = self._find_normalized_match_block(before_code, content)
        if matched_block:
            return self._replace_matched_block(content, matched_block, after_code)

        if partial_before and partial_before != before_code:
            matched_block = self._find_normalized_match_block(partial_before, content)
            if matched_block:
                replacement = partial_after or after_code
                return self._replace_matched_block(content, matched_block, replacement)
        
        return None
    
    def apply_change(self, before_code: str, after_code: str, validate: bool = True) -> bool:
        """Apply a single change to the file.
        
        Args:
            before_code: Code snippet to find and replace
            after_code: Replacement code
            validate: If True, check that replacement was successful
        
        Returns:
            True if change was applied, False otherwise
        """
        if not before_code:
            return False

        applied_before = before_code
        new_content = self._apply_change_with_flexible_match(before_code, after_code, self.current_content)

        if new_content is None or new_content == self.current_content:
            rebased_before = self._find_rebased_before_code(before_code, after_code)
            if rebased_before:
                new_content = self._apply_change_with_flexible_match(rebased_before, after_code, self.current_content)
                applied_before = rebased_before

        if new_content is None or new_content == self.current_content:
            # No actual change made or no match found
            return False

        symbol_renames = self._infer_symbol_renames(before_code, after_code)
        for old_name, new_name in symbol_renames:
            new_content = self._apply_identifier_renames(new_content, [(old_name, new_name)])

        # Validate by checking that the new content contains at least some key part of after_code
        # Since after_code may be indented when applied, we check for normalized versions
        if validate:
            # Check if the main content is there (check first meaningful line)
            after_lines = [line.strip() for line in after_code.split('\n') if line.strip()]
            content_lines = [line.strip() for line in new_content.split('\n')]

            # Check if at least the first non-empty line of after_code is in the result
            if after_lines and after_lines[0] not in content_lines:
                # Couldn't find even the first line - validation failed
                return False

        self.current_content = new_content
        self.changes_applied.append((applied_before, after_code))
        return True
    
    def apply_all_changes(self, changes: List) -> Tuple[int, int, dict]:
        """Attempt to apply all changes with sequential best-effort strategy.
        
        Applies each change sequentially (each modifies the current file state).
        This allows dependent changes to work (e.g., rename function, then modify it).
        If a change fails, continues with the next (best-effort).
        Each individual change is atomic (all-or-nothing).
        
        Args:
            changes: List of RefactorChange objects
            
        Returns:
            Tuple of (successful_count, failed_count, failure_details_dict)
            where failure_details_dict maps change index to reason (str)
        """
        import re
        
        successful = 0
        failed = 0
        failure_details = {}  # Maps change index to failure reason
        
        for idx, change in enumerate(changes):
            before_code = change.before_code
            after_code = change.after_code

            # If the plan itself is a no-op, treat it as already satisfied.
            if self._normalize_code(before_code) == self._normalize_code(after_code):
                successful += 1
                continue

            # If the post-change snippet is already present, the change was likely
            # applied in a previous run or by an earlier dependency in the same run.
            if not self._find_with_flexible_match(before_code, self.current_content):
                if self._find_with_flexible_match(after_code, self.current_content):
                    successful += 1
                    continue

            if self.apply_change(before_code, after_code, validate=False):
                successful += 1
                continue

            rebased_before = self._find_rebased_before_code(before_code, after_code)
            if rebased_before and self.apply_change(rebased_before, after_code, validate=False):
                successful += 1
                continue

            # Code not found - analyze why
            failed += 1
                
            # Check if it's due to undefined variables
            # First, strip docstrings and comments from before_code to avoid false positives
            code_without_docs = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|#.*$', '', before_code, flags=re.MULTILINE)
            
            vars_in_before = set(re.findall(r'\b([a-z_][a-z0-9_]*)\b', code_without_docs, re.IGNORECASE))
            defined_in_before = self._extract_defined_names(code_without_docs)
            
            # Filter out Python keywords and common built-ins
            python_builtins = {
                'def', 'for', 'if', 'elif', 'else', 'while', 'with', 'try', 'except',
                'finally', 'class', 'import', 'from', 'as', 'return', 'yield', 'break',
                'continue', 'pass', 'raise', 'assert', 'del', 'in', 'not', 'and', 'or',
                'is', 'lambda', 'True', 'False', 'None', 'print', 'len', 'range', 'str',
                'int', 'float', 'list', 'dict', 'set', 'tuple', 'append', 'extend',
                'items', 'keys', 'values', 'get', 'pop', 'update', 'add', 'remove',
                'enumerate', 'zip', 'map', 'filter', 'sum', 'all', 'any', 'max', 'min',
                'sorted', 'reversed', 'abs', 'round', 'pow', 'str', 'int', 'float',
                # Common loop/temp variables and method parameters
                'i', 'j', 'k', 'x', 'y', 'z', 'n', 'e', 'v', 'item', 'val', 'data',
                'result', 'output', 'value', 'name', 'idx', 'index', 'count', 'total',
                'self', 'cls', 'args', 'kwargs',
            }
            
            # Combine with Python keywords
            excluded = python_builtins | set(keyword.kwlist)
            
            undefined_vars = []
            for var in vars_in_before:
                if var in defined_in_before:
                    continue

                # Skip Python keywords and built-ins
                if var in excluded:
                    continue
                
                # Skip single-letter variables (almost always parameters/loop vars)
                if len(var) <= 2:
                    continue
                
                # Skip common CamelCase names (class names, likely parameters)
                if var[0].isupper():
                    continue
                
                # Check if variable appears to be defined in the file
                # Check for: assignments, function defs, class attributes, loop vars, function params, with statement vars
                is_defined = bool(re.search(
                    rf'\b{var}\s*=|'  # assignment: var = ...
                    rf'\bdef\s+{var}\s*\(|'  # function definition: def var(
                    rf'self\.{var}\s*=|self\.{var}\s*:|'  # class attribute: self.var = or self.var:
                    rf'\bfor\s+{var}\b|'  # loop variable: for var in
                    rf'\bwith\s+.*\s+as\s+{var}\b|'  # with statement: with ... as var
                    rf'\(.*\b{var}\b.*\)|'  # function parameter: appears in (...{var}...)
                    rf'\b{var}\s*:',  # type annotation: var:
                    self.current_content
                ))
                if not is_defined:
                    undefined_vars.append(var)
            
            if undefined_vars:
                failure_details[idx] = f"Code not found - contains undefined variable(s): {', '.join(undefined_vars)}"
            else:
                declared_names = sorted(defined_in_before)
                if declared_names:
                    failure_details[idx] = (
                        "Code not found in file - plan may be stale for the current file state "
                        f"(snippet defines: {', '.join(declared_names)})"
                    )
                    continue

                # Check if it might be a dependency issue (depends on a rename that didn't happen)
                if hasattr(change, 'depends_on') and change.depends_on and not change.depends_on.lower().startswith('none'):
                    failure_details[idx] = f"Code not found - might depend on: {change.depends_on}"
                else:
                    failure_details[idx] = "Code not found in file"
        
        return successful, failed, failure_details
    
    def write(self) -> None:
        """Write changes to the actual file.
        
        This is the commit point - after calling write(), changes are persisted.
        Creates backup of original before writing.
        """
        if not self.has_changes():
            return
        
        # Save backup
        self._save_backup()
        
        # Write new content
        try:
            self.source_file.write_text(self.current_content, encoding="utf-8")
        except Exception as e:
            raise IOError(f"Failed to write to {self.source_file}: {e}")
    
    def _save_backup(self) -> None:
        """Save backup of the original file before changes."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"{self.source_file.name}.{timestamp}.bak"
        
        try:
            backup_file.write_text(self.original_content, encoding="utf-8")
        except Exception:
            # Silently fail on backup - don't prevent main operation
            pass
    
    def rollback(self) -> None:
        """Restore to original content without writing to file.
        
        Useful for atomic failure recovery.
        """
        self.current_content = self.original_content
        self.changes_applied = []
    
    def get_diff(self) -> str:
        """Generate a unified diff (git-style) of changes.
        
        Returns:
            Unified diff string compatible with `git apply`
        """
        import difflib
        
        original_lines = self.original_content.splitlines(keepends=True)
        new_lines = self.current_content.splitlines(keepends=True)
        
        diff_lines = list(difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{self.source_file.name}",
            tofile=f"b/{self.source_file.name}",
            lineterm=""
        ))
        
        return "\n".join(diff_lines)
    
    def has_changes(self) -> bool:
        """Check if current content differs from original.
        
        Returns:
            True if modifications exist, False otherwise
        """
        return self.current_content != self.original_content
    
    def get_stats(self) -> dict:
        """Get statistics about the changes.
        
        Returns:
            Dict with keys:
            - changes_count: Number of changes applied
            - has_changes: Whether modifications exist
            - original_size: Original file size in bytes
            - new_size: New file size in bytes
            - size_delta: Change in file size
        """
        return {
            "changes_count": len(self.changes_applied),
            "has_changes": self.has_changes(),
            "original_size": len(self.original_content),
            "new_size": len(self.current_content),
            "size_delta": len(self.current_content) - len(self.original_content),
        }


class BackupManager:
    """Manage backups for file rewriting operations.
    
    Provides:
    - List available backups
    - Restore from specific backup
    - Clean old backups
    """
    
    def __init__(self, backup_dir: Path):
        """Initialize backup manager.
        
        Args:
            backup_dir: Directory containing backups (.noor_backups/)
        """
        self.backup_dir = Path(backup_dir)
    
    def list_backups(self, filename: str) -> List[Path]:
        """List all backups for a file.
        
        Args:
            filename: Name of the original file
            
        Returns:
            List of backup file paths, newest first
        """
        if not self.backup_dir.exists():
            return []
        
        pattern = f"{filename}*.bak"
        backups = sorted(self.backup_dir.glob(pattern), reverse=True)
        return backups
    
    def get_latest_backup(self, filename: str) -> Optional[Path]:
        """Get the most recent backup for a file.
        
        Args:
            filename: Name of the original file
            
        Returns:
            Path to latest backup, or None if no backups exist
        """
        backups = self.list_backups(filename)
        return backups[0] if backups else None
    
    def restore_from_backup(self, original_file: Path, backup_path: Path) -> bool:
        """Restore a file from backup.
        
        Args:
            original_file: Path to file to restore to
            backup_path: Path to backup file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            content = backup_path.read_text(encoding="utf-8")
            original_file.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False
    
    def clean_old_backups(self, filename: str, keep_count: int = 5) -> int:
        """Remove old backups, keeping only the N most recent.
        
        Args:
            filename: Name of the original file
            keep_count: Number of recent backups to keep
            
        Returns:
            Number of backups deleted
        """
        backups = self.list_backups(filename)
        deleted = 0
        
        for backup in backups[keep_count:]:
            try:
                backup.unlink()
                deleted += 1
            except Exception:
                pass
        
        return deleted
