"""App startup: load the default scenario, then serve the API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from rakt import llm, store
from rakt.agent import loop
from rakt.channels import telegram_bot
from rakt.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop.reset_scenario(settings.default_scenario)
    await telegram_bot.start()  # no token, or no network → stays off; the sim channel carries everything
    yield
    await telegram_bot.stop()


app = FastAPI(title="RaktTrace", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "now": store.state.clock.now.isoformat(),
        "llm": "on" if llm.status()["enabled"] else "off",
        "telegram": "ok" if telegram_bot.is_running() else "off",
    }
