"""TakenokoAI runner — boots the agent, attaches visualization, and starts a chat loop.

Usage:
    python admin/run_agent.py [--no-viz] [--viz-port 7899] [--config admin/yamls/default.yaml]

The chat loop reads from stdin and sends each line to the Reaction module. The
response from the Motion module is printed to stdout. Type 'exit' or Ctrl-D to quit.

Open http://localhost:7899 to see the live visualization.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from the project root or the admin/ directory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from interface.bus import FamilyPrefix  # noqa: E402
from main import TakenokoAgent  # noqa: E402
from motion.mo_main_module import MotionModule  # noqa: E402
from reaction.re_main_module import ReactionModule  # noqa: E402


async def _readline_async() -> str:
    """Read a line from stdin without blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sys.stdin.readline)


async def _chat_loop(
    agent: TakenokoAgent,
    stop_event: asyncio.Event,
) -> None:
    """Read user input from stdin, forward to Re, print Mo's response."""
    re_module = agent.get_family(FamilyPrefix.Re)
    mo_module = agent.get_family(FamilyPrefix.Mo)

    if not isinstance(re_module, ReactionModule):
        raise TypeError("Expected ReactionModule")
    if not isinstance(mo_module, MotionModule):
        raise TypeError("Expected MotionModule")

    print("\nTakenoko is ready. Type your message and press Enter (Ctrl-D or 'exit' to quit).\n")

    while not stop_event.is_set():
        try:
            sys.stdout.write("You: ")
            sys.stdout.flush()

            line = await _readline_async()

            if not line:  # EOF (Ctrl-D)
                print("\n[runner] Stdin closed — shutting down.")
                stop_event.set()
                break

            text = line.strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                print("[runner] Exiting.")
                stop_event.set()
                break

            # Send to Reaction module (U path → Pr → Mo)
            await re_module.perceive({"text": text})

            # Wait for Mo to produce a response (30s timeout)
            try:
                response = await mo_module.get_output(timeout=30.0)
                print(f"\nTakenoko: {response}\n")
            except TimeoutError:
                print("\n[runner] Timeout waiting for response.\n")

        except (KeyboardInterrupt, asyncio.CancelledError):
            stop_event.set()
            break


async def _run_agent_loops(agent: TakenokoAgent, stop_event: asyncio.Event) -> None:
    """Run all family message loops; stop when stop_event is set."""
    tasks: list[asyncio.Task] = []
    for module in agent._families.values():
        tasks.append(asyncio.create_task(module._message_loop()))

    # Wait until stop is requested
    await stop_event.wait()

    # Cancel all loops
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _run_viz(viz: object, stop_event: asyncio.Event) -> None:
    """Run the visualization server until stop_event is set."""
    viz_task = asyncio.create_task(viz.run())  # type: ignore[attr-defined]
    await stop_event.wait()
    viz_task.cancel()
    try:
        await viz_task
    except asyncio.CancelledError:
        pass


async def amain(config: str, viz_port: int, no_viz: bool) -> None:
    # ── Boot agent ─────────────────────────────────────────────────────────
    print(f"[runner] Booting TakenokoAI from {config} ...")
    agent = TakenokoAgent(config)
    await agent.start()
    print("[runner] Agent started.")

    stop_event = asyncio.Event()

    coros: list = [
        _run_agent_loops(agent, stop_event),
        _chat_loop(agent, stop_event),
    ]

    # ── Optionally attach visualization ────────────────────────────────────
    if not no_viz:
        try:
            from admin.visualization_app import VizBroadcaster
        except ImportError:
            from visualization_app import VizBroadcaster  # type: ignore[no-redef]

        families_dict = {p.value: m for p, m in agent._families.items()}
        viz = VizBroadcaster(port=viz_port, families=families_dict)
        viz.attach(agent._bus)  # type: ignore[arg-type]
        print(f"[runner] Visualization → http://localhost:{viz_port}")
        coros.append(_run_viz(viz, stop_event))

    # ── Run everything concurrently ────────────────────────────────────────
    try:
        await asyncio.gather(*[asyncio.create_task(c) for c in coros])
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        stop_event.set()
        await agent.stop()
        print("[runner] Shutdown complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TakenokoAI agent with chat loop")
    parser.add_argument(
        "--config",
        default="admin/yamls/default.yaml",
        help="Path to YAML config file (default: admin/yamls/default.yaml)",
    )
    parser.add_argument(
        "--viz-port",
        type=int,
        default=7899,
        help="WebSocket visualization server port (default: 7899)",
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Disable visualization server",
    )
    args = parser.parse_args()

    try:
        asyncio.run(amain(args.config, args.viz_port, args.no_viz))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
