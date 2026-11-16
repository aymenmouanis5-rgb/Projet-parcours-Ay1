import argparse
import time
from pathlib import Path

from filets.runner import TIMINGS, run
from filets.sim import MODES

parser = argparse.ArgumentParser(prog="filets", description="Run one FILETS simulation.")
parser.add_argument("--agents", type=int, default=4)
parser.add_argument("--seasons", type=int, default=10)
parser.add_argument("--seed", type=int, default=1)
parser.add_argument("--mode", choices=MODES, default="talk",
                    help="talk: LLM with evening talk, silent: LLM without it, "
                         "rules and quota: no LLM references")
parser.add_argument("--timing", choices=TIMINGS, default="sync",
                    help="sync: everyone acts at the same step, async: each fisher at his own pace")
parser.add_argument("--season-seconds", type=float, default=20.0,
                    help="real seconds in one simulated season, in async timing")
parser.add_argument("--model", help="give every fisher this Ollama model instead of the mixed sizes")
parser.add_argument("--no-hint", action="store_true",
                    help="remove the safe limit and the per-fisher share from the prompts")
args = parser.parse_args()
if args.timing == "async" and args.mode in ("rules", "quota"):
    parser.error("async timing needs LLM fishers: use --mode talk or silent")

label =f"_{args.model.replace(':', '-')}" if args.model else ""
label += "_nohint" if args.no_hint else ""
label += f"_{args.agents}f" if args.agents != 4 else ""
label += "_async" if args.timing == "async" else ""
out = Path("runs") / f"{time.strftime('%Y%m%d-%H%M%S')}_{args.mode}{label}_s{args.seed}"
summary = run(args.agents, args.seasons, args.mode, args.seed, out, args.model, not args.no_hint,
              args.timing, args.season_seconds)

usage = summary["usage"]
print(f"\nsurvived {summary['seasons_survived']} seasons, collapsed={summary['collapsed']}")
print(f"{usage['calls']} calls, {usage['input_tokens'] + usage['output_tokens']} tokens, "
      f"{usage['seconds']:.0f}s LLM time, {usage['failed_attempts']} failed attempts, "
      f"{usage['embed_calls']} embed calls, {summary['events_rejected']} events rejected")
if "timing_detail" in summary:
    print(summary["timing_detail"])
print(f"logs: {out}")
