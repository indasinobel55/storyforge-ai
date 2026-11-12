"""Command line entry point for the autonomous video generation agent.

Examples::

    python -m agent.autonomous prompts/obsidian_spire.md
    python -m agent.autonomous prompts/obsidian_spire.md --dry-run
    python -m agent.autonomous story.md --no-narration --transition crossfade
    python -m agent.autonomous story.md -o outputs/my_film --resume
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agent.autonomous",
        description="Autonomously generate a narrated cinematic film from a master prompt document.",
    )
    parser.add_argument("prompt", type=Path, help="Path to the master prompt markdown file")
    parser.add_argument("-o", "--out", type=Path, default=None, help="Output directory (default: outputs/<slug>)")
    parser.add_argument(
        "--provider",
        choices=["simulated", "taaft"],
        default="simulated",
        help="Generation provider: 'simulated' renders FFmpeg placeholder clips; 'taaft' drives the real TAAFT website",
    )
    parser.add_argument(
        "--tier",
        choices=["fast", "quality"],
        default="quality",
        help="TAAFT generation tier; 'quality' is the site's slow, high-detail mode (default)",
    )
    parser.add_argument(
        "--enable-taaft",
        action="store_true",
        help="Explicit consent gate for real TAAFT automation (same as TAAFT_LOCAL_ENABLED=1)",
    )
    parser.add_argument(
        "--login-taaft",
        action="store_true",
        help="Open a headed Chrome window, wait for you to log into TAAFT, then verify the session and quota",
    )
    parser.add_argument(
        "--taaft-profile",
        type=Path,
        default=None,
        help="Persistent Chrome profile directory for the TAAFT session (default: .taaft_chrome_profile)",
    )
    parser.add_argument(
        "--taaft-headless",
        action="store_true",
        help="Run the TAAFT browser headless (default is headed for Cloudflare/CAPTCHA trust)",
    )
    parser.add_argument("--poll", type=int, default=None, help="TAAFT job poll interval in seconds (default 20)")
    parser.add_argument(
        "--job-timeout",
        type=int,
        default=None,
        help="Per-scene TAAFT job timeout in seconds (default 3600; quality tier jobs take minutes)",
    )
    parser.add_argument("--enhance", action="store_true", help="Let TAAFT enhance prompts on the site")
    parser.add_argument("--chrome", default=None, help="Path to chrome.exe used for the TAAFT browser")
    parser.add_argument(
        "--transition",
        choices=["fade", "crossfade", "none"],
        default="fade",
        help="Scene transition style (default: fade keeps the runtime exact)",
    )
    parser.add_argument("--no-narration", action="store_true", help="Disable SAPI voiceover narration")
    parser.add_argument("--no-ambience", action="store_true", help="Disable the procedural ambient sound bed")
    parser.add_argument("--voice", default=None, help="SAPI voice name (e.g. 'Microsoft Zira Desktop')")
    parser.add_argument("--narration-rate", type=int, default=1, help="SAPI speech rate from -10 to 10 (default: 1)")
    parser.add_argument("--no-resume", action="store_true", help="Regenerate every scene even if clips exist")
    parser.add_argument("--fps", type=float, default=24.0, help="Output frame rate (default: 24)")
    parser.add_argument(
        "--scene-seconds",
        type=float,
        default=None,
        help="Override the per-scene duration from the master prompt",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and write plan.json only, no generations")
    return parser


def config_taaft_env(args) -> bool:
    import os

    return os.environ.get("TAAFT_LOCAL_ENABLED", "0") == "1"


async def main_async(argv: list[str] | None = None) -> int:
    from .runner import AutonomousConfig, AutonomousPipeline

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.prompt.exists():
        print(f"error: master prompt not found: {args.prompt}", file=sys.stderr)
        return 2

    config = AutonomousConfig(
        prompt_path=args.prompt,
        output_dir=args.out,
        provider=args.provider,
        tier=args.tier,
        transition=args.transition,
        with_narration=not args.no_narration,
        narration_voice=args.voice,
        narration_rate=args.narration_rate,
        with_ambience=not args.no_ambience,
        resume=not args.no_resume,
        fps=args.fps,
        scene_seconds_override=args.scene_seconds,
        taaft_enabled=args.enable_taaft or config_taaft_env(args),
        taaft_profile_dir=args.taaft_profile,
        taaft_headless=args.taaft_headless,
        taaft_poll_seconds=args.poll or 20,
        taaft_job_timeout_seconds=args.job_timeout or 3600,
        taaft_enhance=args.enhance,
        chrome_path=args.chrome,
    )

    if args.login_taaft:
        from .taaft_login import run_login

        report = await asyncio.to_thread(
            run_login,
            profile_dir=config.taaft_profile_dir,
            chrome_path=config.chrome_path,
            headless=config.taaft_headless,
        )
        print(f"account: {report}")
        return 0

    if args.dry_run:
        from .masterprompt import parse_master_prompt_file

        _, plan = parse_master_prompt_file(args.prompt)
        out_dir = config.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        from agent.core.util import write_json

        write_json(out_dir / "plan.json", plan.model_dump())
        print(f"[dry-run] {len(plan.scenes)} scenes x {plan.scenes[0].duration:.0f}s -> {out_dir / 'plan.json'}")
        for scene in plan.scenes:
            print(f"  scene {scene.scene_number:02d}: {scene.title}")
        return 0

    pipeline = AutonomousPipeline(config)
    try:
        result = await pipeline.run()
    except Exception as error:  # noqa: BLE001
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"final: {result.final_path}")
    print(f"report: {result.report_path}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
