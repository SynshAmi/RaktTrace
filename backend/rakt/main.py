"""App startup: load the default scenario, start the bot and the auto clock, then serve the API (BUILD §5.3)."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from rakt import llm, store
from rakt.agent import loop
from rakt.api import benchmark, demo, requests, sim
from rakt.api import map as map_api
from rakt.api import llm as llm_api
from rakt.channels import telegram_bot
from rakt.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    with store.lock:
        loop.reset_scenario(settings.default_scenario)
    await telegram_bot.start()  # no token, or no network → stays off; the sim channel carries everything
    auto_clock = asyncio.create_task(demo.run_auto_clock())
    yield
    auto_clock.cancel()
    with suppress(asyncio.CancelledError):
        await auto_clock
    await telegram_bot.stop()


app = FastAPI(title="RaktTrace", lifespan=lifespan)
for module in (requests, sim, demo, llm_api, benchmark, map_api):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    with store.lock:
        now = store.state.clock.now.isoformat()
    return {
        "ok": True,
        "now": now,
        "llm": "on" if llm.reading_with_llm() else "off",
        "telegram": "ok" if telegram_bot.is_running() else "off",
    }
