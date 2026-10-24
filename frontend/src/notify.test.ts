// node --experimental-strip-types --test (npm test). Decisions shaped like the backend's, from S1–S3 runs.
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Decision, RequestStatus } from "./api.ts";
import { advance, DURATION_MS, emptyQueue, enqueue, notesFor, severity, type Queue } from "./notify.ts";

let n = 0;
const d = (status: RequestStatus, trigger: string, actions: string[] = [], p: [number, number] = [0.5, 0.5]): Decision =>
  ({ id: `dec_${++n}`, request_id: "RT-1", at: `2026-10-24T18:${String(n).padStart(2, "0")}:00+05:30`, trigger,
     p_before: p[0], p_after: p[1], status, actions, summary: `${trigger}.` });

test("severity: a status reaching FULFILLED or FAILED, an L2 alert or a widening are critical; the rest routine", () => {
  const open = d("OPEN", "new request");
  assert.equal(severity(d("FULFILLED", "Centre B: unit ready"), d("SECURED", "x")), "fulfilled");
  assert.equal(severity(d("FULFILLED", "deadline reached"), d("FULFILLED", "x")), "routine");  // already fulfilled
  assert.equal(severity(d("FAILED", "deadline reached", ["failed"]), open), "failed");
  assert.equal(severity(d("OPEN", "staff overdue", ["L2 alert"]), open), "escalation");
  assert.equal(severity(d("OPEN", "half the time has gone", ["widen to 40 km"]), open), "escalation");
  assert.equal(severity(d("COVERED", "Nikhil R. replied: STANDBY"), open), "routine");
});

test("a Next event that records one decision gives exactly one note, about that decision", () => {
  const log = [d("OPEN", "new request"), d("OPEN", "Centre A offered 1; reserved 1", [], [0.85, 0.93])];
  const notes = notesFor(log, 1, "Next event");
  assert.equal(notes.length, 1);
  assert.equal(notes[0].title, "Centre A offered 1; reserved 1");
  assert.match(notes[0].body, /85% → 93%/);
});

test("a jump batches routine decisions into one summary with the P movement; critical ones get their own notes", () => {
  const log = [d("OPEN", "new request", [], [0, 0.65]),
    d("OPEN", "Centre A has none", [], [0.65, 0.69]), d("OPEN", "Fatima D. · 1 replied: ACTIVE", [], [0.69, 0.88]),
    d("COVERED", "Nikhil R. replied: STANDBY", [], [0.88, 0.98]), d("COVERED", "Varun A. didn't reply in 30 min"),
    d("OPEN", "Centre B hasn't tapped", ["L2 alert"])];
  const notes = notesFor(log, 1, "+1 h");
  assert.deepEqual(notes.map((x) => x.severity), ["routine", "escalation"]);
  assert.equal(notes[0].title, "+1 h: 4 updates");
  assert.match(notes[0].body, /65% → 50%/);  // first p_before to last p_after of the routine ones
  assert.match(notes[0].body, /and 1 more/);
  assert.match(notes[0].body, /Status now COVERED/);
});

test("critical notes queue in order behind the active one; none is replaced or dropped", () => {
  const a = notesFor([d("OPEN", "x"), d("OPEN", "staff overdue", ["L2 alert"])], 1, "Auto")[0];
  const b = notesFor([d("OPEN", "x"), d("OPEN", "widened", ["widen to 40 km"])], 1, "Auto")[0];
  const c = notesFor([d("SECURED", "x"), d("FAILED", "deadline reached", ["failed"])], 1, "Auto")[0];
  let q: Queue = advance(enqueue(emptyQueue, [a]));
  assert.equal(q.active?.id, a.id);
  q = enqueue(q, [b]);
  q = enqueue(q, [c]);
  assert.equal(q.active?.id, a.id);  // still showing; nothing overlaps
  const shown = [q.active!.id];
  while (q.active) {
    q = advance({ ...q, active: null });  // the active note's time ran out
    if (q.active) shown.push(q.active.id);
  }
  assert.deepEqual(shown, [a.id, b.id, c.id]);
});

test("routine summaries never pile up: a newer one replaces a waiting one, critical notes go first", () => {
  const r1 = notesFor([d("OPEN", "x"), d("OPEN", "a"), d("OPEN", "b")], 1, "Auto")[0];
  const r2 = notesFor([d("OPEN", "x"), d("OPEN", "c"), d("OPEN", "e")], 1, "Auto")[0];
  const crit = notesFor([d("SECURED", "x"), d("FULFILLED", "Centre B: unit ready")], 1, "Auto")[0];
  let q = enqueue({ active: crit, waiting: [] }, [r1]);
  q = enqueue(q, [r2]);
  assert.deepEqual(q.waiting.map((x) => x.id), [r2.id]);
  q = enqueue(q, [notesFor([d("OPEN", "x"), d("OPEN", "o", ["L2 alert"])], 1, "Auto")[0]]);
  q = advance({ ...q, active: null });
  assert.equal(q.active?.severity, "escalation");
});

test("failure and fulfilment stay longest; routine fades quickly", () => {
  assert.ok(DURATION_MS.failed >= DURATION_MS.escalation && DURATION_MS.fulfilled >= DURATION_MS.escalation);
  assert.ok(DURATION_MS.escalation > DURATION_MS.routine && DURATION_MS.routine <= 4000);
});
