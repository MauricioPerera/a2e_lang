"""File watcher for auto-recompilation."""

from __future__ import annotations

import os
import sys
import time


def watch_and_compile(
    filepath: str,
    *,
    spec: bool = False,
    pretty: bool = False,
    interval: float = 0.5,
) -> None:
    """Watch a .a2e file and recompile on changes.

    Args:
        filepath: Path to the .a2e file.
        spec: Use official A2E spec format.
        pretty: Pretty-print output.
        interval: Polling interval in seconds.
    """
    from .compiler import Compiler
    from .compiler_spec import SpecCompiler
    from .errors import A2ELangError
    from .parser import parse
    from .validator import Validator

    print(f"👀 Watching {filepath} (Ctrl+C to stop)")

    last_mtime = 0.0
    last_hash = ""

    while True:
        try:
            mtime = os.path.getmtime(filepath)
            if mtime == last_mtime:
                time.sleep(interval)
                continue

            last_mtime = mtime

            with open(filepath, encoding="utf-8") as f:
                source = f.read()

            # Skip if content hasn't actually changed
            content_hash = str(hash(source))
            if content_hash == last_hash:
                time.sleep(interval)
                continue
            last_hash = content_hash

            # Clear screen
            print("\033[2J\033[H", end="")
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] Compiling {filepath}...")
            print("-" * 60)

            try:
                workflow = parse(source)
                validator = Validator()
                errors = validator.validate(workflow)

                if errors:
                    print(f"❌ {len(errors)} validation error(s):")
                    for e in errors:
                        print(f"  {e}")
                else:
                    compiler = SpecCompiler() if spec else Compiler()
                    if pretty:
                        output = compiler.compile_pretty(workflow)
                    else:
                        output = compiler.compile(workflow)

                    print(f"✅ Compiled ({len(workflow.operations)} ops)")
                    print("-" * 60)
                    print(output)

            except A2ELangError as e:
                print(f"❌ Error: {e}")

            print()
            print(f"👀 Watching for changes... (Ctrl+C to stop)")

        except FileNotFoundError:
            print(f"❌ File not found: {filepath}")
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n🛑 Stopped watching.")
            break

        time.sleep(interval)
