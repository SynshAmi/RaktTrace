# RaktTrace

**A yes isn't blood.** RaktTrace is an agent that keeps working an urgent blood request until a blood centre confirms the units are ready.

When a hospital is short of blood, families are told to "arrange blood", and a request counts as done the moment someone says yes. But listings are often stale, "kal aaunga" means tomorrow, donated blood needs hours of testing, and donors get deferred at screening. RaktTrace:

1. **Checks stock first**, and asks centres to reserve units.
2. **Messages only the donors truly needed**, and only if their blood can be ready in time.
3. **Checks every reply against the deadline**, testing included.
4. **Keeps backups** and promotes them when someone is deferred.
5. **Closes only on the blood centre's confirmation**, then stands donors down and tells the family to stop forwarding.
6. **Escalates early** with a plain-English handover when it won't make it.

The planner makes every decision. An LLM reads messy messages (English/Hindi/Hinglish) and writes escalation briefs, with a rule-based fallback.

**Stack:** Python · FastAPI · python-telegram-bot · OpenAI-compatible LLMs · React + Vite + TypeScript.

**Demo:** synthetic Bengaluru city. Real Telegram messages to judges and staff; simulated donors and centres; a "today's workflow" lane side by side; a live benchmark.

Team Veritas (HX-BDXL): Suryansh Singh, Aditya Dev · AgentOps 2026.

Docs: start with [`CLAUDE.md`](CLAUDE.md) and [`docs/SPEC.md`](docs/SPEC.md).
