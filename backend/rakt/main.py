"""App startup: load the default scenario, then serve the API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from rakt import llm, store
from rakt.config import settings
from rakt.sim.scenarios import load_scenario


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.set_state(load_scenario(settings.default_scenario))
    yield


app = FastAPI(title="RaktTrace", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "now": store.state.clock.now.isoformat(),
        "llm": "on" if llm.status()["enabled"] else "off",
        "telegram": "off",
    }
