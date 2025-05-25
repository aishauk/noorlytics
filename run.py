import click
from noorlytics import analyzer, license_audit, llm_interface, logger

@click.group()
def cli():
    """Noorlytics CLI - Analyze and refactor Python codebases using AI."""
    pass

@cli.command()
@click.argument('path')
@click.option('--mode', default='ollama', type=click.Choice(['ollama', 'openai']), help='LLM backend to use.')
def analyze(path, mode):
    """Analyze a file or directory for technical debt."""
    click.echo(f"Analyzing {path} using mode {mode}...")
    analyzer.run_analysis(path, mode)

@cli.command()
@click.argument('path')
@click.option('--mode', default='ollama', type=click.Choice(['ollama', 'openai']))
def suggest(path, mode):
    """Suggest refactorings for the given file."""
    click.echo(f"Generating suggestions for {path} using {mode}...")
    with open(path, "r") as f:
        code = f.read()
    suggestions = llm_interface.suggest_refactorings(code, engine=mode)
    click.echo("\n💡 Suggestions:\n")
    click.echo(suggestions)

@cli.command()
@click.argument('path')
@click.option('--mode', default='ollama', type=click.Choice(['ollama', 'openai']))
def refactor(path, mode):
    """Apply basic refactorings to the code."""
    click.echo(f"Refactoring {path} using {mode}... (TODO: Not yet implemented)")
    # TODO: Implement auto_refactor functionality in next version.
    # analyzer.auto_refactor(path, mode)

@cli.command('add-tests')
@click.argument('path')
@click.option('--mode', default='ollama', type=click.Choice(['ollama', 'openai']))
def add_tests(path, mode):
    """Generate unit test stubs for given module."""
    click.echo(f"Generating test stubs for {path} using {mode}...")
    with open(path, "r") as f:
        code = f.read()
    test_code = llm_interface.generate_test_stubs(code, engine=mode)
    click.echo("\n🧪 Generated Test Stubs:\n")
    click.echo(test_code)

if __name__ == '__main__':
    cli()