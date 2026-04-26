import sys
import typer
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.syntax import Syntax
from rich.prompt import Confirm

# Fix for Windows console emoji crashes (forces UTF-8 output)
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from recall import db, ai
from recall.models import SavedCommand
from recall.config import get_api_key

app = typer.Typer(
    name="recall",
    help="🧠 AI-powered command assistant for developers",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

ACCENT = "cyan"
SUCCESS = "green"
WARN = "yellow"
ERROR = "red"


def _require_api_key():
    if not get_api_key():
        console.print(
            Panel(
                "[yellow]ANTHROPIC_API_KEY is not set.[/yellow]\n\n"
                "Run: [cyan]export ANTHROPIC_API_KEY=your_key_here[/cyan]\n"
                "Or add it to a [cyan].env[/cyan] file in your project root.",
                title="[red]Missing API Key[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)


def _print_command_result(result: dict):
    """Pretty-print the ask command result."""
    cmd_text = Text(result["command"], style="bold cyan")

    content = Text()
    content.append(result["command"], style="bold cyan")
    content.append("\n\n")
    content.append("📖 ", style="dim")
    content.append(result["explanation"], style="white")

    if result.get("alternatives"):
        content.append("\n\n")
        content.append("↳ Also: ", style="dim")
        content.append(result["alternatives"][0], style="dim cyan")

    console.print(
        Panel(
            content,
            title=f"[dim]📦 {result.get('tool', 'cli')}[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    tags = result.get("tags", [])
    if tags:
        console.print(f"  [dim]tags: {', '.join(tags)}[/dim]")


import re

def _fill_placeholders(command: str) -> str:
    """Detect <placeholder> tokens and prompt the user to fill them in."""
    placeholders = re.findall(r"<([^>]+)>", command)
    if not placeholders:
        return command
    console.print(f"  [yellow]Command has {len(placeholders)} placeholder(s) to fill in:[/yellow]")
    for ph in placeholders:
        value = typer.prompt(f"  Enter value for [cyan]<{ph}>[/cyan]")
        command = command.replace(f"<{ph}>", value, 1)
    return command


def _print_commands_table(commands: list[SavedCommand], title: str = "Saved Commands"):
    if not commands:
        console.print(f"[{WARN}]No commands found.[/{WARN}]")
        return

    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Command", style="bold white", min_width=30)
    table.add_column("Description", style="white", min_width=25)
    table.add_column("Tool", style="cyan", width=10)
    table.add_column("Tags", style="dim", width=18)
    table.add_column("Uses", style="green", width=5, justify="right")

    for cmd in commands:
        table.add_row(
            str(cmd.id),
            cmd.command,
            cmd.description,
            cmd.tool,
            cmd.tags_str(),
            str(cmd.use_count),
        )

    console.print(table)


# ─── Commands ──────────────────────────────────────────────────────────────────

@app.command()
def ask(
    query: str = typer.Argument(..., help="Natural language description of what you want to do"),
    save: bool = typer.Option(False, "--save", "-s", help="Save the result to your library"),
):
    """[cyan]Ask[/cyan] for a command using plain English.\n
    [dim]Example: recall ask "squash last 3 git commits"[/dim]"""
    _require_api_key()

    with console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
        try:
            result = ai.ask_command(query)
        except Exception as e:
            console.print(f"[{ERROR}]AI error: {e}[/{ERROR}]")
            raise typer.Exit(1)

    _print_command_result(result)

    # Auto-prompt to save
    if save or Confirm.ask("\n  [dim]Save this to your library?[/dim]", default=False):
        db.init_db()
        saved_id = db.save_command(
            SavedCommand(
                command=result["command"],
                description=result["explanation"],
                tags=result.get("tags", []),
                tool=result.get("tool", "general"),
            )
        )
        console.print(f"  [{SUCCESS}]✓ Saved as #{saved_id}[/{SUCCESS}]")


@app.command()
def explain(
    command: str = typer.Argument(..., help="The CLI command to explain"),
    save: bool = typer.Option(False, "--save", "-s", help="Save the command to your library"),
):
    """[cyan]Explain[/cyan] what any CLI command does.\n
    [dim]Example: recall explain "docker run -it --rm -v $(pwd):/app ubuntu bash"[/dim]"""
    _require_api_key()

    with console.status("[cyan]Analyzing...[/cyan]", spinner="dots"):
        try:
            result = ai.explain_command(command)
        except Exception as e:
            console.print(f"[{ERROR}]AI error: {e}[/{ERROR}]")
            raise typer.Exit(1)

    # Header panel
    content = Text()
    content.append(command, style="bold cyan")
    content.append("\n\n")
    content.append("📖 ", style="dim")
    content.append(result["summary"], style="white")
    console.print(Panel(content, title="[dim]Command[/dim]", border_style="cyan", padding=(1, 2)))

    # Breakdown table
    breakdown = result.get("breakdown", [])
    if breakdown:
        table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
        table.add_column("Part", style="cyan", min_width=25)
        table.add_column("Meaning", style="white")
        for item in breakdown:
            table.add_row(item["part"], item["meaning"])
        console.print(table)

    # Warning
    warning = result.get("warning", "")
    if warning:
        console.print(
            Panel(f"[yellow]⚠ {warning}[/yellow]", border_style="yellow", padding=(0, 2))
        )

    if save or Confirm.ask("\n  [dim]Save this to your library?[/dim]", default=False):
        db.init_db()
        saved_id = db.save_command(
            SavedCommand(
                command=command,
                description=result["summary"],
                tags=result.get("tags", []),
                tool=result.get("tool", "general"),
            )
        )
        console.print(f"  [{SUCCESS}]✓ Saved as #{saved_id}[/{SUCCESS}]")


@app.command()
def save(
    command: str = typer.Argument(..., help="The command to save"),
    description: str = typer.Option(..., "--desc", "-d", help="Short description"),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags"),
    tool: str = typer.Option("general", "--tool", help="CLI tool name (git, docker, etc.)"),
):
    """[cyan]Save[/cyan] a command manually to your library.\n
    [dim]Example: recall save "git stash pop" --desc "restore last stash" --tags git,stash[/dim]"""
    db.init_db()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    saved_id = db.save_command(
        SavedCommand(command=command, description=description, tags=tag_list, tool=tool)
    )
    console.print(f"  [{SUCCESS}]✓ Saved as #{saved_id}[/{SUCCESS}]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search term (matches command, description, tags, tool)"),
):
    """[cyan]Search[/cyan] your saved command library.\n
    [dim]Example: recall search "stash"[/dim]"""
    db.init_db()
    results = db.search_commands(query)
    _print_commands_table(results, title=f'Search: "{query}"')


@app.command(name="list")
def list_cmds(
    tool: Optional[str] = typer.Option(None, "--tool", "-t", help="Filter by tool name"),
):
    """[cyan]List[/cyan] all saved commands.\n
    [dim]Example: recall list --tool git[/dim]"""
    db.init_db()
    commands = db.list_commands(tool=tool)
    title = f"Saved Commands — {tool}" if tool else "All Saved Commands"
    _print_commands_table(commands, title=title)


@app.command()
def delete(
    id: int = typer.Argument(..., help="ID of the command to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """[cyan]Delete[/cyan] a saved command by ID.\n
    [dim]Example: recall delete 3[/dim]"""
    db.init_db()
    if not yes:
        confirmed = Confirm.ask(f"  Delete command #{id}?", default=False)
        if not confirmed:
            console.print("  [dim]Cancelled.[/dim]")
            raise typer.Exit()
    if db.delete_command(id):
        console.print(f"  [{SUCCESS}]✓ Deleted #{id}[/{SUCCESS}]")
    else:
        console.print(f"  [{ERROR}]No command found with id #{id}[/{ERROR}]")



@app.command(name="do")
def do_goal(
    goal: str = typer.Argument(..., help="High-level goal to accomplish (can require multiple commands)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm every step without prompting"),
):
    """[cyan]Do[/cyan] something that requires multiple commands — AI plans & executes the steps.\n
    [dim]Example: recall do "create a redis instance with redisinsight GUI"[/dim]"""
    _require_api_key()

    with console.status("[cyan]Planning steps...[/cyan]", spinner="dots"):
        try:
            steps = ai.ask_pipeline(goal)
        except Exception as e:
            console.print(f"[{ERROR}]AI error: {e}[/{ERROR}]")
            raise typer.Exit(1)

    if not steps:
        console.print(f"[{WARN}]AI returned no steps for this goal.[/{WARN}]")
        raise typer.Exit(1)

    _print_plan_table(steps, goal)

    if not yes and not Confirm.ask("\n  [dim]Execute this plan?[/dim]", default=False):
        console.print("  [dim]Cancelled.[/dim]")
        raise typer.Exit()

    _execute_steps(steps, yes)



def _print_plan_table(steps: list[dict], goal: str = ""):
    from rich.markup import escape
    table = Table(
        title=f'Plan: "{goal}"' if goal else "Current Plan",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Step", style="bold white", min_width=22)
    table.add_column("Command", style="cyan", min_width=35)
    table.add_column("Tool", style="dim", width=10)
    for i, s in enumerate(steps, 1):
        table.add_row(str(i), escape(s.get("step", "")), escape(s.get("command", "")), escape(s.get("tool", "")))
    console.print(table)


def _edit_plan(steps: list[dict]) -> list[dict]:
    """Interactive plan editor — returns the (possibly modified) steps list."""
    while True:
        console.print(
            "\n  [dim]Edit:[/dim] "
            "[cyan]e <#>[/cyan] edit cmd  "
            "[cyan]m <#> <#>[/cyan] move/swap  "
            "[cyan]d <#>[/cyan] delete  "
            "[cyan]a[/cyan] add  "
            "[cyan]done[/cyan] proceed\n"
        )
        raw = typer.prompt("  edit", default="done", prompt_suffix=" → ").strip()
        parts = raw.split()
        action = parts[0].lower() if parts else "done"

        if action == "done":
            break

        elif action == "e" and len(parts) == 2 and parts[1].isdigit():
            idx = int(parts[1]) - 1
            if 0 <= idx < len(steps):
                console.print(f"  Current: [cyan]{steps[idx]['command']}[/cyan]")
                steps[idx]["command"] = typer.prompt("  New command")
                steps[idx]["step"]    = typer.prompt("  New step title", default=steps[idx]["step"])
            else:
                console.print(f"  [{ERROR}]Invalid step number.[/{ERROR}]")

        elif action == "m" and len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            a, b = int(parts[1]) - 1, int(parts[2]) - 1
            if 0 <= a < len(steps) and 0 <= b < len(steps):
                steps[a], steps[b] = steps[b], steps[a]
                console.print(f"  [{SUCCESS}]Swapped steps {a+1} and {b+1}.[/{SUCCESS}]")
            else:
                console.print(f"  [{ERROR}]Invalid step numbers.[/{ERROR}]")

        elif action == "d" and len(parts) == 2 and parts[1].isdigit():
            idx = int(parts[1]) - 1
            if 0 <= idx < len(steps):
                removed = steps.pop(idx)
                console.print(f"  [{SUCCESS}]Deleted: {removed['step']}[/{SUCCESS}]")
            else:
                console.print(f"  [{ERROR}]Invalid step number.[/{ERROR}]")

        elif action == "a":
            title = typer.prompt("  Step title")
            cmd   = typer.prompt("  Command")
            tool  = typer.prompt("  Tool", default="general")
            steps.append({"step": title, "command": cmd, "explanation": title, "tool": tool})
            console.print(f"  [{SUCCESS}]Added step #{len(steps)}.[/{SUCCESS}]")

        else:
            console.print("  [dim]Unknown — try: done | e 2 | m 1 3 | d 2 | a[/dim]")

        _print_plan_table(steps)

    return steps


def _execute_steps(steps: list[dict], yes: bool):
    """Walk through steps: fill placeholders, run/skip/abort."""
    import subprocess
    total = len(steps)
    for i, s in enumerate(steps, 1):
        console.rule(f"[cyan]Step {i}/{total}[/cyan] — {s['step']}")
        console.print(f"  [dim]{s.get('explanation', '')}[/dim]")
        run_cmd = _fill_placeholders(s["command"])
        console.print(Panel(Text(run_cmd, style="bold cyan"), border_style="cyan", padding=(0, 2)))

        if not yes:
            choice = typer.prompt(
                "  [r]un / [s]kip / [a]bort", default="r", prompt_suffix=" → "
            ).strip().lower()
            if choice == "a":
                console.print(f"  [{WARN}]Aborted at step {i}.[/{WARN}]")
                raise typer.Exit(1)
            if choice == "s":
                console.print("  [dim]Skipped.[/dim]")
                continue

        proc = subprocess.run(run_cmd, shell=True)
        if proc.returncode == 0:
            console.print(f"  [{SUCCESS}]✓ Step {i} done.[/{SUCCESS}]")
        else:
            console.print(f"  [{ERROR}]✗ Step {i} failed (exit {proc.returncode}).[/{ERROR}]")
            if not yes and not Confirm.ask("  Continue anyway?", default=False):
                raise typer.Exit(proc.returncode)

    console.print(Panel(f"[{SUCCESS}]✓ All steps complete![/{SUCCESS}]", border_style="green", padding=(0, 2)))


@app.command(name="change")
def change_plan(
    goal: str = typer.Argument(..., help="High-level goal to plan and customize before running"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmations after editing"),
):
    """[cyan]Change[/cyan] — AI generates a plan, you edit it, then it executes.\n
    [dim]Lets you reorder, modify, add, or delete steps before running.[/dim]\n
    [dim]Example: recall change "setup redis with redisinsight"[/dim]"""
    _require_api_key()

    with console.status("[cyan]Planning steps...[/cyan]", spinner="dots"):
        try:
            steps = ai.ask_pipeline(goal)
        except Exception as e:
            console.print(f"[{ERROR}]AI error: {e}[/{ERROR}]")
            raise typer.Exit(1)

    if not steps:
        console.print(f"[{WARN}]AI returned no steps.[/{WARN}]")
        raise typer.Exit(1)

    _print_plan_table(steps, goal)
    console.print(f"\n  [yellow]Review the plan — edit before executing.[/yellow]")
    steps = _edit_plan(steps)

    if not steps:
        console.print(f"  [{WARN}]No steps to run.[/{WARN}]")
        raise typer.Exit()

    _print_plan_table(steps, goal)
    if not yes and not Confirm.ask("\n  [dim]Execute this plan?[/dim]", default=False):
        console.print("  [dim]Cancelled.[/dim]")
        raise typer.Exit()

    _execute_steps(steps, yes)


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context):
    """🧠 [bold cyan]Recall[/bold cyan] — AI-powered command assistant for developers."""
    if ctx.invoked_subcommand is None:
        console.print(
            Panel(
                "[bold cyan]recall[/bold cyan] — AI-powered command assistant\n\n"
                "[dim]Commands:[/dim]\n"
                "  [cyan]ask[/cyan]      Natural language → command\n"
                "  [cyan]explain[/cyan]  Understand any command\n"
                "  [cyan]save[/cyan]     Save a command manually\n"
                "  [cyan]search[/cyan]   Search your library\n"
                "  [cyan]list[/cyan]     List all saved commands\n"
                "  [cyan]delete[/cyan]   Remove a saved command\n\n"
                "[dim]Run [cyan]recall --help[/cyan] for details.[/dim]",
                border_style="cyan",
                padding=(1, 3),
            )
        )

@app.command()
def run(
    ref: str = typer.Argument(..., help="Command ID (e.g. 3) or a search keyword"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """[cyan]Run[/cyan] a saved command by ID or keyword.\n
    [dim]Example: recall run 3[/dim]\n
    [dim]Example: recall run stash[/dim]"""
    import subprocess
    db.init_db()

    # Resolve: numeric id → direct lookup, else search
    cmd: SavedCommand | None = None
    if ref.isdigit():
        matches = [c for c in db.list_commands() if c.id == int(ref)]
        if matches:
            cmd = matches[0]
    else:
        matches = db.search_commands(ref)
        if len(matches) == 1:
            cmd = matches[0]
        elif len(matches) > 1:
            _print_commands_table(matches, title=f'Multiple matches for "{ref}" — pick one')
            id_choice = typer.prompt("  Enter ID to run")
            chosen = [c for c in matches if str(c.id) == id_choice.strip()]
            if chosen:
                cmd = chosen[0]

    if not cmd:
        # Not in library — ask AI
        _require_api_key()
        console.print(f"  [dim]Not found in library. Asking AI for: [cyan]{ref}[/cyan]...[/dim]")
        with console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
            try:
                ai_result = ai.ask_command(ref)
            except Exception as e:
                console.print(f"  [{ERROR}]AI error: {e}[/{ERROR}]")
                raise typer.Exit(1)

        _print_command_result(ai_result)

        # Let user pick an alternative if any exist
        alternatives = [a for a in ai_result.get("alternatives", []) if a]
        chosen_command = ai_result["command"]
        if alternatives:
            options = [ai_result["command"]] + alternatives
            console.print("  [dim]Choose a command to run:[/dim]")
            for i, opt in enumerate(options):
                marker = "[cyan]0[/cyan]" if i == 0 else f"[cyan]{i}[/cyan]"
                console.print(f"    {marker}  {opt}")
            pick = typer.prompt("  Enter number", default="0")
            try:
                chosen_command = options[int(pick)]
            except (ValueError, IndexError):
                console.print(f"  [{WARN}]Invalid choice, using default.[/{WARN}]")

        run_cmd = _fill_placeholders(chosen_command)


        if not yes and not Confirm.ask("\n  [dim]Execute this command?[/dim]", default=False):
            console.print("  [dim]Cancelled.[/dim]")
            raise typer.Exit()

        import subprocess
        proc = subprocess.run(run_cmd, shell=True)

        if proc.returncode == 0:
            if Confirm.ask("  [dim]Save this to your library?[/dim]", default=False):
                saved_id = db.save_command(
                    SavedCommand(
                        command=ai_result["command"],
                        description=ai_result["explanation"],
                        tags=ai_result.get("tags", []),
                        tool=ai_result.get("tool", "general"),
                    )
                )
                console.print(f"  [{SUCCESS}]✓ Saved as #{saved_id}[/{SUCCESS}]")
        else:
            console.print(f"  [{ERROR}]✗ Command exited with code {proc.returncode}[/{ERROR}]")
            raise typer.Exit(proc.returncode)
        return


    # Show what will run
    console.print(
        Panel(
            Text(cmd.command, style="bold cyan"),
            title=f"[dim]#{cmd.id} — {cmd.tool}[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    run_cmd = _fill_placeholders(cmd.command)

    if not yes and not Confirm.ask("  [dim]Execute this command?[/dim]", default=False):
        console.print("  [dim]Cancelled.[/dim]")
        raise typer.Exit()

    import subprocess
    result = subprocess.run(run_cmd, shell=True)
    if result.returncode == 0:
        db.increment_use(cmd.id)
        console.print(f"\n  [{SUCCESS}]✓ Done (use count: {cmd.use_count + 1})[/{SUCCESS}]")
    else:
        console.print(f"\n  [{ERROR}]✗ Command exited with code {result.returncode}[/{ERROR}]")
        raise typer.Exit(result.returncode)



if __name__ == "__main__":
    app()
