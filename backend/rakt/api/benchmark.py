"""Benchmark endpoints (BUILD §5.3). A run happens in a separate process, so it never touches the live demo's
state, never sends a Telegram message and never calls an LLM provider (cached readings only)."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rakt.sim.benchmark import results_path

router = APIRouter()
BACKEND_DIR = Path(__file__).resolve().parents[2]
ESSENTIAL = {"today", "rakttrace"}
RUN_TIMEOUT_S = 600


class BenchmarkBody(BaseModel):
    n: int = Field(default=500, ge=1, le=1000)
    seed: int = 2026
    reader: Literal["llm", "rules"] = "llm"
    policies: list[str] | None = None
    regime: Literal["nominal", "stress"] = "nominal"


@router.post("/benchmark")
async def run(body: BenchmarkBody) -> dict:
    if body.policies is not None and not set(body.policies) <= ESSENTIAL:
        raise HTTPException(422, "Only the essential tier (today, rakttrace) is built; broadcast and threshold "
                                 "come after the rehearsal (BUILD §6.3)")
    if body.regime != "nominal":
        raise HTTPException(422, "The stress regime is an optional tier and isn't built yet")
    env = {**os.environ, "TELEGRAM_BOT_TOKEN": ""}
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "rakt.sim.benchmark", "--n", str(body.n), "--seed", str(body.seed),
        "--reader", body.reader, "--json", cwd=BACKEND_DIR, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), RUN_TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(504, "The benchmark took too long")
    if proc.returncode != 0:
        raise HTTPException(500, "The benchmark failed: " + err.decode(errors="replace").strip().splitlines()[-1])
    return json.loads(out.decode().strip().splitlines()[-1])


@router.get("/benchmark/cached")
def cached(seed: int = 2026, regime: str = "nominal") -> dict:
    """The last saved run for this seed (the committed seed-2026 run is the one shown on stage)."""
    path = results_path(seed, regime)
    if not path.exists():
        raise HTTPException(404, f"No cached run for seed {seed} ({regime})")
    return json.loads(path.read_text(encoding="utf-8"))
