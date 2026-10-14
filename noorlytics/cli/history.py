"""CLI commands for decision history and version comparison."""

import click
from typing import Optional

from noorlytics.decision_store import DecisionStore
from noorlytics.decision_history import DecisionHistory


@click.group()
def history():
    """Track and compare decision versions across assessments.
    
    DESCRIPTION:
    View the evolution of decisions over time, including:
    - Timeline of all assessments for a manifest
    - Changes between versions (added, removed, modified)
    - Version-by-version analysis
    
    SUBCOMMANDS:
    - show       Display assessment timeline
    - diff       Compare two assessment versions
    
    EXAMPLES:
    - noor history show requirements.txt            # All versions
    - noor history show requirements.txt --all-versions  # No limit
    - noor history diff requirements.txt            # Compare last two
    """
    pass


@history.command(name="show")
@click.argument("manifest_path")
@click.option(
    "--all-versions",
    is_flag=True,
    help="Show all versions (default: last 5)",
)
@click.option(
    "--format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format",
)
@click.option(
    "--db",
    type=click.Path(),
    default=None,
    help="Path to decisions database",
)
def show_history(
    manifest_path: str,
    all_versions: bool,
    format: str,
    db: Optional[str],
):
    """Show assessment history timeline for a manifest file.
    
    PURPOSE:
    Display the chronological history of all decisions for a file,
    showing how recommendations have evolved over assessments.
    
    PARAMETERS:
    - manifest_path (required): Path to manifest file (e.g., requirements.txt)
    - --all-versions: Show all versions (default: last 5)
    - --format: Output format (markdown, json)
      * markdown (default): Human-readable timeline
      * json: Machine-readable structured data
    - --db: Custom database path
    
    OUTPUTS:
    - Timeline with timestamps for each assessment
    - Summary of changes in each version
    - Trend analysis of decision evolution
    
    EXAMPLES:
    - noor history show requirements.txt            # Last 5 versions
    - noor history show requirements.txt --all-versions  # All versions
    - noor history show pyproject.toml --format json # JSON format
    - noor history show src/ --all-versions         # All versions as JSON
    """
    try:
        store = DecisionStore(db)
        history_tracker = DecisionHistory(store)
        
        timeline = history_tracker.get_assessment_timeline(manifest_path)
        
        if not timeline:
            click.echo(f"No assessment history found for {manifest_path}")
            return
        
        if format == "json":
            import json
            output = []
            for snapshot in timeline:
                output.append({
                    "version": snapshot.assessment_version,
                    "created_at": snapshot.created_at.isoformat() if hasattr(snapshot.created_at, 'isoformat') else str(snapshot.created_at),
                    "decision_count": snapshot.decision_count,
                    "by_priority": snapshot.by_priority,
                })
            click.echo(json.dumps(output, indent=2))
        
        else:  # markdown format
            markdown = history_tracker.generate_history_markdown(manifest_path)
            click.echo(markdown)
    
    except Exception as e:
        click.echo(f"Error retrieving history: {e}", err=True)
        raise click.Abort()


@history.command(name="diff")
@click.argument("manifest_path")
@click.option(
    "--from",
    "version_from",
    type=int,
    default=None,
    help="Starting version (default: latest-1)",
)
@click.option(
    "--to",
    "version_to",
    type=int,
    default=None,
    help="Ending version (default: latest)",
)
@click.option(
    "--format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format",
)
@click.option(
    "--show-details",
    is_flag=True,
    help="Include full decision changes",
)
@click.option(
    "--db",
    type=click.Path(),
    default=None,
    help="Path to decisions database",
)
def diff_versions(
    manifest_path: str,
    version_from: Optional[int],
    version_to: Optional[int],
    format: str,
    show_details: bool,
    db: Optional[str],
):
    """Compare decision changes between two assessment versions.
    
    PURPOSE:
    Analyze what changed between two assessment runs, including:
    - New decisions added
    - Decisions resolved or removed
    - Priority/category changes
    - Recommendation updates
    
    PARAMETERS:
    - manifest_path (required): Path to manifest file
    - --from: Starting version (default: second-latest)
    - --to: Ending version (default: latest)
    - --format: Output format (markdown, json)
    - --show-details: Include full decision changes with rationale
    - --db: Custom database path
    
    OUTPUTS:
    - Added decisions (new in later version)
    - Removed decisions (no longer present)
    - Modified decisions (changed priority/status)
    - Summary of impact and trends
    
    EXAMPLES:
    - noor history diff requirements.txt            # Compare last two
    - noor history diff requirements.txt --from 1 --to 3  # Specific versions
    - noor history diff requirements.txt --format json    # JSON format
    - noor history diff requirements.txt --show-details   # Full changes
    """
    try:
        store = DecisionStore(db)
        history_tracker = DecisionHistory(store)
        
        # Determine versions if not provided
        if version_from is None or version_to is None:
            latest = history_tracker.get_latest_version(manifest_path)
            if not latest or latest < 2:
                click.echo(f"Not enough versions to compare for {manifest_path}")
                return
            
            if version_to is None:
                version_to = latest
            if version_from is None:
                version_from = latest - 1
        
        # Get diff
        diff = history_tracker.get_assessment_diff(manifest_path, version_from, version_to)
        
        if format == "json":
            import json
            output = {
                "from_version": version_from,
                "to_version": version_to,
                "added": [d.id for d in diff.added],
                "removed": [d.id for d in diff.removed],
                "modified": [d.id for d in diff.modified],
                "priority_changed": [
                    {"id": change[0], "old": change[1].value, "new": change[2].value}
                    for change in diff.priority_changed
                ],
                "has_changes": diff.has_changes,
            }
            if show_details:
                output["details"] = {
                    "added_decisions": [
                        {"id": d.id, "title": d.title, "priority": d.priority.value}
                        for d in diff.added
                    ],
                    "removed_decisions": [
                        {"id": d.id, "title": d.title, "priority": d.priority.value}
                        for d in diff.removed
                    ],
                }
            click.echo(json.dumps(output, indent=2))
        
        else:  # markdown format
            markdown = history_tracker.generate_delta_markdown(
                manifest_path, version_from, version_to
            )
            click.echo(markdown)
            
            if show_details:
                click.echo("\n## Full Diff Details\n")
                if diff.added:
                    click.echo("### Added Decisions ✅\n")
                    for d in diff.added:
                        click.echo(f"- **{d.id}**: {d.title} (P{d.priority.value[1:]})")
                
                if diff.removed:
                    click.echo("\n### Removed Decisions ❌\n")
                    for d in diff.removed:
                        click.echo(f"- **{d.id}**: {d.title} (P{d.priority.value[1:]})")
                
                if diff.priority_changed:
                    click.echo("\n### Priority Changes 📊\n")
                    for change in diff.priority_changed:
                        click.echo(f"- **{change[0]}**: {change[1].value} → {change[2].value}")
    
    except Exception as e:
        click.echo(f"Error comparing versions: {e}", err=True)
        raise click.Abort()


@history.command(name="compare")
@click.argument("manifest_path")
@click.option(
    "--all-versions",
    is_flag=True,
    help="Include all versions (default: last 5)",
)
@click.option(
    "--format",
    type=click.Choice(["markdown", "table"]),
    default="markdown",
    help="Output format",
)
@click.option(
    "--db",
    type=click.Path(),
    default=None,
    help="Path to decisions database",
)
def compare_versions(
    manifest_path: str,
    all_versions: bool,
    format: str,
    db: Optional[str],
):
    """Generate comparison matrix across assessment versions.
    
    Examples:
        noor history compare requirements.txt
        noor history compare requirements.txt --all-versions
        noor history compare pyproject.toml --format table
    """
    try:
        store = DecisionStore(db)
        history_tracker = DecisionHistory(store)
        
        timeline = history_tracker.get_assessment_timeline(manifest_path)
        
        if not timeline or len(timeline) < 2:
            click.echo(f"Not enough versions to compare for {manifest_path}")
            return
        
        matrix = history_tracker.generate_comparison_matrix(manifest_path)
        click.echo(matrix)
    
    except Exception as e:
        click.echo(f"Error generating comparison matrix: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    history()
