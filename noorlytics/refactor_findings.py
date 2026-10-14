"""Local Python refactor findings and deterministic plan coverage."""

import ast
import copy
import hashlib
import io
import re
import tokenize
from dataclasses import asdict, dataclass


DETECTOR_VERSION = "2"


@dataclass(frozen=True)
class RefactorFinding:
    id: str
    rule: str
    scope: str
    line: int
    evidence: str
    message: str
    requires_review: bool = False


def collect_refactor_findings(filename: str, content: str) -> list[RefactorFinding]:
    if not filename.lower().endswith(".py"):
        return []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    findings = []

    def visit_scope(container, prefix=""):
        for node in container.body:
            if isinstance(node, ast.ClassDef):
                visit_scope(node, prefix + node.name + ".")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scope = prefix + node.name
                found_rules = set()

                def add(rule, evidence_node, message, review=False):
                    if rule in found_rules:
                        return
                    found_rules.add(rule)
                    evidence = ast.get_source_segment(content, evidence_node) or ""
                    digest = hashlib.sha256(f"{scope}:{rule}:{evidence}".encode()).hexdigest()[:12]
                    findings.append(RefactorFinding(
                        f"RF-{digest}", rule, scope, evidence_node.lineno,
                        evidence, message, review,
                    ))

                def inspect(current):
                    if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)) and current is not node:
                        return
                    if isinstance(current, ast.Compare) and any(isinstance(op, (ast.Eq, ast.NotEq)) for op in current.ops):
                        if any(isinstance(part, ast.Constant) and part.value is None for part in [current.left] + current.comparators):
                            add("none_comparison", current, "Review equality comparison with None; use identity checks only when equivalent.", True)
                    if isinstance(current, ast.BinOp) and isinstance(current.op, ast.Add):
                        if any(isinstance(part, ast.Constant) and isinstance(part.value, str) for part in ast.walk(current)):
                            add("string_concatenation", current, "Consider f-string formatting; preserve operand conversion and error behavior.")
                    if isinstance(current, ast.Constant) and type(current.value) in (int, float) and current.value not in (0, 1, -1):
                        add("numeric_literal", current, "Review unexplained numeric literals; consider named constants without changing business rules.", True)
                    if isinstance(current, ast.For):
                        iterator = current.iter
                        if isinstance(iterator, ast.Call) and isinstance(iterator.func, ast.Name) and iterator.func.id == "range":
                            if any(isinstance(part, ast.Call) and isinstance(part.func, ast.Name) and part.func.id == "len" for part in ast.walk(iterator)):
                                add("indexed_iteration", current, "Consider direct iteration or enumerate; preserve mutation and indexing semantics.")
                        for part in ast.walk(current):
                            if isinstance(part, ast.AugAssign) and isinstance(part.op, ast.Add):
                                add("manual_accumulation", current, "Review manual totals/counts; consider sum and len while preserving empty-input and numeric behavior.")
                            if isinstance(part, ast.Assign) and isinstance(part.value, ast.BinOp) and isinstance(part.value.op, ast.Add):
                                if any(ast.unparse(target) == ast.unparse(part.value.left) for target in part.targets):
                                    add("manual_accumulation", current, "Review manual totals/counts; consider sum and len while preserving empty-input and numeric behavior.")
                    if isinstance(current, ast.Call) and isinstance(current.func, ast.Attribute) and current.func.attr == "split":
                        if any(isinstance(arg, ast.Constant) and arg.value == "@" for arg in current.args):
                            add("email_validation_policy", current, "Review ad-hoc email splitting. Do not tighten accepted addresses without an explicit validation policy.", True)
                    for child in ast.iter_child_nodes(current):
                        inspect(child)

                inspect(node)
                if len(node.body) >= 2:
                    assignment, returned = node.body[-2:]
                    if isinstance(assignment, ast.Assign) and len(assignment.targets) == 1 and isinstance(assignment.targets[0], ast.Name):
                        if isinstance(returned, ast.Return) and isinstance(returned.value, ast.Name) and returned.value.id == assignment.targets[0].id:
                            add("redundant_return_assignment", assignment, "Return the final expression directly without changing the preceding business rules.")
                visit_scope(node, scope + ".")

    visit_scope(tree)
    return findings


def finding_checklist(findings: list[RefactorFinding]) -> str:
    return "\n".join(
        f"{finding.id} | {finding.scope}:{finding.line} | {finding.rule} | "
        f"{'REVIEW' if finding.requires_review else 'CANDIDATE'} | {finding.message}\n"
        f"Evidence: {finding.evidence}"
        for finding in findings
    )


def plan_coverage(findings: list[RefactorFinding], changes, markdown: str) -> list[dict]:
    results = []
    for finding in findings:
        references = [
            index for index, change in enumerate(changes)
            if finding.id in re.findall(r"\bRF-[a-f0-9]{12}\b", change.title + "\n" + change.problem_statement)
            and change.before_code != change.after_code
        ]
        unresolved = re.search(
            rf"^Unresolved:\s*{re.escape(finding.id)}\s*[-:]\s*(.+)$", markdown, re.MULTILINE
        )
        status = "planned" if references else "unresolved" if unresolved else "omitted"
        reason = unresolved.group(1).strip() if unresolved and not references else ""
        if references:
            applications = [changes[index].application_status for index in references]
            if all(application == "applied" for application in applications):
                status = "applied"
            elif all(application == "skipped" for application in applications):
                status = "skipped"
                reason = "; ".join(changes[index].application_reason for index in references)
            elif "applied" in applications and "skipped" in applications:
                status = "partial"
        results.append({
            **asdict(finding), "status": status, "change_indices": references,
            "reason": reason,
        })
    return results


def grounded_refactor_plan(filename: str, content: str, markdown: str) -> str:
    """Prefer source-derived replacements for a small set of supported patterns."""
    if not filename.lower().endswith(".py"):
        return markdown
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return markdown
    from .refactor_executor import ChangePriority, RefactorChange, RefactorPlanParser

    findings = collect_refactor_findings(filename, content)
    replacements = {}
    lines = content.splitlines()
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    for function in functions:
        updated = copy.deepcopy(function)
        addressed = set()
        for index, statement in enumerate(updated.body):
            if not isinstance(statement, ast.For) or statement.orelse or not isinstance(statement.target, ast.Name):
                continue
            iterator = statement.iter
            if not (isinstance(iterator, ast.Call) and isinstance(iterator.func, ast.Name) and iterator.func.id == "range" and len(iterator.args) == 1 and not iterator.keywords):
                continue
            length = iterator.args[0]
            if not (isinstance(length, ast.Call) and isinstance(length.func, ast.Name) and length.func.id == "len" and len(length.args) == 1 and not length.keywords and isinstance(length.args[0], ast.Name)):
                continue
            if not statement.body:
                continue
            assignment = statement.body[0]
            if not (isinstance(assignment, ast.Assign) and len(assignment.targets) == 1 and isinstance(assignment.targets[0], ast.Name) and isinstance(assignment.value, ast.Subscript)):
                continue
            sequence = length.args[0].id
            if not (isinstance(assignment.value.value, ast.Name) and assignment.value.value.id == sequence and isinstance(assignment.value.slice, ast.Name) and assignment.value.slice.id == statement.target.id):
                continue
            index_uses = [node for node in ast.walk(updated) if isinstance(node, ast.Name) and node.id == statement.target.id and isinstance(node.ctx, ast.Load)]
            sequence_uses = [node for node in ast.walk(updated) if isinstance(node, ast.Name) and node.id == sequence]
            if len(index_uses) != 1 or len(sequence_uses) != 2 or len(statement.body) < 2:
                continue
            statement.target = copy.deepcopy(assignment.targets[0])
            statement.iter = copy.deepcopy(length.args[0])
            statement.body = statement.body[1:]
            addressed.add("indexed_iteration")

        has_formatting_finding = any(finding.scope == function.name and finding.rule == "string_concatenation" for finding in findings)
        if len(updated.body) >= 2 and not has_formatting_finding:
            assignment, returned = updated.body[-2:]
            if isinstance(assignment, ast.Assign) and len(assignment.targets) == 1 and isinstance(assignment.targets[0], ast.Name):
                if isinstance(returned, ast.Return) and isinstance(returned.value, ast.Name) and returned.value.id == assignment.targets[0].id:
                    uses = [node for node in ast.walk(updated) if isinstance(node, ast.Name) and node.id == assignment.targets[0].id and isinstance(node.ctx, ast.Load)]
                    if len(uses) == 1:
                        returned.value = assignment.value
                        updated.body.pop(-2)
                        addressed.add("redundant_return_assignment")
        if not addressed:
            continue
        before = "\n".join(lines[function.lineno - 1:function.end_lineno])
        if any(token.type == tokenize.COMMENT for token in tokenize.generate_tokens(io.StringIO(before).readline)) or function.decorator_list:
            continue
        after = ast.unparse(ast.fix_missing_locations(updated))
        ids = [finding.id for finding in findings if finding.scope == function.name and finding.rule in addressed]
        replacements[function.name] = RefactorChange(
            ChangePriority.LOW, f"Simplify iteration/return in `{function.name}`",
            " ".join(ids) + " Source-derived replacement; preserves preceding branches and list returns.",
            before, after, [], "Compare outputs, empty inputs, and default branches.", {},
            "Direct iteration assumes ordinary non-mutating sequence traversal.",
        )
    if not replacements:
        return markdown

    parser = RefactorPlanParser(markdown)
    changes = parser.parse()
    preserved = []
    for change in changes:
        names = set(re.findall(r"^\s*def\s+(\w+)\s*\(", change.before_code, re.MULTILINE))
        if names & replacements.keys():
            continue
        preserved.append(change)
    parser.changes = list(replacements.values()) + preserved
    unresolved = "\n".join(line for line in markdown.splitlines() if line.startswith("Unresolved:"))
    return parser.to_markdown() + ("\n\n" + unresolved if unresolved else "")