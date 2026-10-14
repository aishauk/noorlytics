"""CLI commands for decision analytics and metrics."""

import click
from typing import Optional

from noorlytics.decision_store import DecisionStore
from noorlytics.decision_analytics import DecisionAnalytics


@click.group()
def metrics():
    """View analytics dashboards and decision metrics.
    
    DESCRIPTION:
    Access decision analytics including:
    - Overall metrics and KPIs
    - Customer-specific analysis
    - Priority distribution and trends
    - Category breakdown and patterns
    
    SUBCOMMANDS:
    - dashboard     Overall metrics dashboard
    - customer      Customer-specific metrics
    - trend         Historical trend analysis
    - by-category   Category breakdown
    
    EXAMPLES:
    - noor metrics dashboard                        # All-time overview
    - noor metrics customer --customer "Acme Corp"  # For one customer
    - noor metrics trend --period 30                # Last 30 days
    - noor metrics by-category                      # Category analysis
    """
    pass


@metrics.command(name="dashboard")
@click.option(
    "--period",
    type=click.Choice(["7", "30", "90", "all"]),
    default="all",
    help="Time period (default: all-time)",
)
@click.option(
    "--format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format",
)
@click.option(
    "--output",
    type=click.Path(),
    default=None,
    help="Save to file (default: stdout)",
)
@click.option(
    "--db",
    type=click.Path(),
    default=None,
    help="Path to decisions database",
)
def show_dashboard(
    period: str,
    format: str,
    output: Optional[str],
    db: Optional[str],
):
    """Show comprehensive metrics dashboard with decision analytics.
    
    PURPOSE:
    Display overview of all decisions including:
    - Total decision count and distribution
    - Priority breakdown (P1-P4 counts)
    - Category distribution
    - Timeline and trend information
    - Key metrics and KPIs
    
    PARAMETERS:
    - --period: Time period for analysis
      * 7: Last 7 days
      * 30: Last 30 days
      * 90: Last 90 days
      * all (default): All-time data
    - --format: Output format (markdown, json)
    - --output: Save to file (default: display in terminal)
    - --db: Custom database path
    
    OUTPUTS:
    - Summary table with decision counts
    - Priority distribution chart
    - Category breakdown
    - Trend summary
    
    EXAMPLES:
    - noor metrics dashboard                        # All-time
    - noor metrics dashboard --period 30            # Last 30 days
    - noor metrics dashboard --format json          # JSON format
    - noor metrics dashboard --output dashboard.md  # Save to file
    """
    try:
        store = DecisionStore(db)
        analytics = DecisionAnalytics(store)
        
        # Convert period to days
        days = None if period == "all" else int(period)
        
        dashboard = analytics.generate_metrics_dashboard(period=period, days=days)
        
        if output:
            with open(output, "w") as f:
                f.write(dashboard)
            click.echo(f"Dashboard saved to {output}")
        else:
            click.echo(dashboard)
    
    except Exception as e:
        click.echo(f"Error generating dashboard: {e}", err=True)
        raise click.Abort()


@metrics.command(name="customer")
@click.argument("customer_name")
@click.option(
    "--period",
    type=click.Choice(["7", "30", "90", "all"]),
    default="all",
    help="Time period",
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
def customer_report(
    customer_name: str,
    period: str,
    format: str,
    db: Optional[str],
):
    """Generate customer-specific decision metrics and analysis.
    
    PURPOSE:
    Show decision analytics for a specific customer including:
    - Total decisions and breakdown by priority
    - Decision categories distribution
    - Implementation rate and timeline
    - Key metrics for customer engagement
    
    PARAMETERS:
    - customer_name (required): Name of the customer to analyze
    - --period: Time period for analysis (7, 30, 90, all)
    - --format: Output format (markdown, json)
    - --db: Custom database path
    
    OUTPUTS:
    - Customer summary and KPIs
    - Priority distribution specific to customer
    - Category breakdown for customer decisions
    - Implementation metrics
    
    EXAMPLES:
    - noor metrics customer "Acme Corp"             # Full history
    - noor metrics customer "Acme Corp" --period 30 # Last 30 days
    - noor metrics customer "Acme Corp" --format json # JSON format
    - noor metrics customer "Acme Corp" --period 7  # Weekly report
    """
    try:
        store = DecisionStore(db)
        analytics = DecisionAnalytics(store)
        
        if format == "json":
            import json
            metrics = analytics.get_customer_metrics(customer_name)
            output = {
                "customer": metrics.customer_name,
                "total_decisions": metrics.total_decisions,
                "by_priority": metrics.by_priority,
                "by_category": metrics.by_category,
                "implementation_rate": f"{metrics.implementation_rate * 100:.1f}%",
                "avg_time_to_implement": f"{metrics.avg_time_to_implement:.1f} days",
            }
            click.echo(json.dumps(output, indent=2))
        
        else:  # markdown format
            report = analytics.generate_customer_report(customer_name)
            click.echo(report)
    
    except Exception as e:
        click.echo(f"Error generating customer report: {e}", err=True)
        raise click.Abort()


@metrics.command(name="by-category")
@click.option(
    "--period",
    type=click.Choice(["7", "30", "90", "all"]),
    default="all",
    help="Time period",
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
def category_breakdown(
    period: str,
    format: str,
    db: Optional[str],
):
    """Show decision breakdown by category with distribution analysis.
    
    PURPOSE:
    Analyze how decisions are distributed across categories:
    - Dependency management
    - Security issues
    - Performance optimizations
    - Code quality improvements
    - Architecture decisions
    
    PARAMETERS:
    - --period: Time period for analysis (7, 30, 90, all)
    - --format: Output format (markdown, json)
    - --db: Custom database path
    
    OUTPUTS:
    - Category-wise decision count
    - Priority distribution within each category
    - Percentage breakdown
    - Trends and patterns by category
    
    EXAMPLES:
    - noor metrics by-category                      # All-time breakdown
    - noor metrics by-category --period 30          # Last 30 days
    - noor metrics by-category --format json        # JSON format
    """
    try:
        store = DecisionStore(db)
        analytics = DecisionAnalytics(store)
        
        days = None if period == "all" else int(period)
        metrics = analytics.get_metrics_summary(period=period, days=days)
        
        if format == "json":
            import json
            output = {
                "period": period,
                "by_category": metrics.by_category,
                "total": metrics.total_decisions,
            }
            click.echo(json.dumps(output, indent=2))
        
        else:  # markdown format
            from tabulate import tabulate
            table_data = []
            for category, count in sorted(metrics.by_category.items()):
                percentage = (count / metrics.total_decisions * 100) if metrics.total_decisions > 0 else 0
                table_data.append([category.replace("_", " ").title(), count, f"{percentage:.1f}%"])
            
            click.echo(f"# Decision Breakdown by Category ({period} days)\n")
            click.echo(tabulate(
                table_data,
                headers=["Category", "Count", "Percentage"],
                tablefmt="github"
            ))
    
    except Exception as e:
        click.echo(f"Error generating category breakdown: {e}", err=True)
        raise click.Abort()


@metrics.command(name="trend")
@click.option(
    "--days",
    type=int,
    default=90,
    help="Analyze last N days (default: 90)",
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
def trend_analysis(
    days: int,
    format: str,
    db: Optional[str],
):
    """Generate historical trend analysis and forecasting.
    
    PURPOSE:
    Analyze how decision metrics have evolved over time:
    - Decision volume trends
    - Priority distribution changes
    - Category popularity shifts
    - Implementation rate trends
    - Velocity and backlog analysis
    
    PARAMETERS:
    - --days: Period to analyze (default: 90 days)
      * 7: Weekly analysis
      * 30: Monthly analysis
      * 90: Quarterly analysis
      * Custom: Any number of days
    - --format: Output format (markdown, json)
    - --db: Custom database path
    
    OUTPUTS:
    - Time-based decision volume chart
    - Priority trend visualization
    - Category trend analysis
    - Forecast and velocity metrics
    
    EXAMPLES:
    - noor metrics trend                            # Last 90 days
    - noor metrics trend --days 30                  # Last 30 days
    - noor metrics trend --format json              # JSON format
    - noor metrics trend --days 7                   # Weekly trend
    """
    try:
        store = DecisionStore(db)
        analytics = DecisionAnalytics(store)
        
        if format == "json":
            import json
            # Get metrics for different periods
            trend_7d = analytics.get_metrics_summary(period="7d", days=7)
            trend_30d = analytics.get_metrics_summary(period="30d", days=30)
            trend_90d = analytics.get_metrics_summary(period="90d", days=90)
            
            output = {
                "7_days": {
                    "total": trend_7d.total_decisions,
                    "by_priority": trend_7d.by_priority,
                },
                "30_days": {
                    "total": trend_30d.total_decisions,
                    "by_priority": trend_30d.by_priority,
                },
                "90_days": {
                    "total": trend_90d.total_decisions,
                    "by_priority": trend_90d.by_priority,
                },
            }
            click.echo(json.dumps(output, indent=2))
        
        else:  # markdown format
            report = analytics.generate_trend_report(days=days)
            click.echo(report)
    
    except Exception as e:
        click.echo(f"Error generating trend report: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    metrics()
