# Synaptic Fabric — Plain-English Guide

A friendly walkthrough of what the system does, why it matters, and how the pieces fit together — written for anyone who hasn't seen the technical report.

---

## What is this project, in one sentence?

It's a **virtual factory floor** that runs on your laptop, watches its own machines for early signs of failure, and fixes them automatically — without sending any data to the cloud.

Think of it as a fitness tracker for industrial machinery: it constantly monitors the machines' "vital signs", flags anything unusual, explains what's wrong, and even performs the equivalent of a quick tune-up before things break.

---

## The factory we're simulating

We're pretending to run a small four-machine production line:

| Stage | Machine | What it does |
|---|---|---|
| 1 | **M_1 — Induction Motor** | The starter — applies twisting force (torque) to drive the line. |
| 2 | **M_2 — Industrial Gearbox** | Transfers that force; if the motor jolts, the gearbox shakes. |
| 3 | **M_3 — CNC Milling Tool** | Does the precision cutting; if the gearbox shakes, this one heats up. |
| 4 | **M_4 — Robotic Sorting Arm** | Picks up finished parts; if the mill overheats, this one strains. |

Notice the pattern: **a problem upstream becomes a problem downstream.** A torque spike at the motor causes vibration in the gearbox a few seconds later, which causes heat buildup in the mill, which strains the robot arm. Real factories work this way — and our system simulates it accurately.

This domino effect isn't random. The simulator uses a "delay queue" — when the motor spikes, the gearbox sees it exactly two seconds later. The mill sees the gearbox vibration three seconds after that. This realistic timing is what lets the AI learn to predict failures *before* they happen.

---

## The "AI brain" — three models working together

We don't trust just one AI to decide whether a machine is in trouble. Three different models each look at the data from a different angle, and their answers get combined into a single risk score.

### 1. The Physics Model (PINN)

This one knows how heat actually works in metal. It reads the current load and air temperature and calculates *what temperature the machine should be at*. If the actual reading is much cooler than what physics says it should be, that's a warning sign — heat is building up faster than it can dissipate, which means a thermal runaway is starting.

**Why it matters:** This isn't pattern matching from past failures. It's grounded in real physics, so it works even on situations the AI has never seen before.

### 2. The Chain Model (GNN)

This one looks at all four machines as a connected line and asks "given that M_2 is shaking, how worried should we be about M_3?". It naturally accounts for the fact that one machine's problems affect its neighbours.

### 3. The Pattern Model (classical ML)

This is the traditional approach: trained on historical data, it knows what a "soon to fail" machine looks like statistically. It takes the current readings and outputs a probability of failure.

### How they combine

The final risk score is a weighted blend:
- **40%** classical ML
- **20%** anomaly detection
- **15%** chain-aware GNN
- **15%** physics PINN
- **10%** ML-based anomaly model

Plus a hard safety override: if temperature, vibration, or wear cross dangerous thresholds, risk is forced to at least 90% regardless of what the AIs say. We never want the system to "explain away" a glaringly hot machine.

A risk score of **85% or higher = Critical**, **50–85% = Warning**, below 50% = Healthy.

---

## What you actually see — the dashboard

Open `http://localhost:3000` in a browser and you'll see a **mission control** screen with these parts:

- **A 3D model** of all four machines, colored green / yellow / red based on health.
- **One card per machine** showing the live numbers: temperature, twisting force, tool wear, vibration, plus a failure-risk percentage and an estimate of remaining useful life.
- **Plant-level stats** — overall health score, which machine is the most worrying right now, and how many machines need attention.
- **Live alerts** that pop up automatically when any machine crosses a Warning or Critical threshold.
- **Three collapsible panels** (closed by default to keep the view clean) for maintenance history, log downloads, and live temperature charts.
- **A chat assistant** in the bottom right corner — ask it questions like "what's the temperature of M_3?" or "why is the motor unstable?".

Every machine card has two action buttons:
- **Perform Maintenance** — instantly tunes up that machine.
- **Inject Spike** — for hypothetical "what if" testing (more on this below).

---

## How the system fixes problems on its own

The most interesting part of the project is the **closed loop**: when a machine gets sick, the system actually does something about it without anyone clicking anything.

Here's what happens behind the scenes when a machine drifts into trouble:

1. The dashboard's main service notices that, say, M_3 has crossed into Warning.
2. It fires a message to a separate piece of software called **n8n** — think of it as a workflow engine, like a digital flowchart that runs automatically.
3. n8n decides what to do based on severity. For a serious problem it asks a small AI language model (running locally) to write a short explanation of *why* this is happening — citing which sensors are off and what likely caused it.
4. n8n then sends the corrective instruction back to the dashboard service.
5. The dashboard service performs maintenance on the affected machine — resetting tool wear, cooling it down, dropping vibration — and a popup appears at the top of the screen saying "Maintenance completed for M_3".

There's also a **backup safety net**: if the machine has been Critical for ten seconds straight (and isn't already cooling down from a recent maintenance), the dashboard service runs maintenance itself, even if the workflow engine isn't reachable. Belt and suspenders.

---

## The "what-if" feature

Operators sometimes want to ask: *"What would happen if M_2 suddenly developed a serious vibration problem? Would the whole plant be affected, or just M_2?"*

That's what the **Inject Spike** button does. You click it on any machine, type in fake values for temperature, vibration, wear, or torque, and click Apply.

Two interesting things happen:

1. **The chain effect ripples through.** If you spike M_2, M_3 also gets affected (because in real life, gearbox vibration drives mill heat). M_4 gets a smaller effect. M_1 gets the smallest effect of all (a "reflected" influence). The exact attenuation factors are: origin = 100%, one machine downstream = 60%, two downstream = 40%, three downstream = 25%, and small ratios (20%, 10%, 5%) for upstream "reflection".

2. **It's fully reversible.** The system snapshots every affected machine's *real* state before you spike it. The moment you click Perform Maintenance on **any** of the affected machines, the entire plant snaps back to its pre-spike state.

This makes the feature safe for training operators or running drills — you can simulate a catastrophic failure, see exactly how the dashboard reacts, then undo it with a single click.

Every spike and every revert is logged with a special **WHAT-IF** badge, so it's never confused with real maintenance in the historical records.

---

## Maintenance history & downloads

Every time anything maintenance-related happens — whether you clicked the button, the dwell-time rule fired automatically, the workflow engine triggered a reset, or someone injected a what-if spike — it's recorded in a database with:

- The exact timestamp (UTC)
- The machine
- What action was taken (Manual, Auto, Spike, Revert)
- Who triggered it (dashboard, automatic rule, workflow engine, what-if simulation)
- The machine's health and risk score at the moment
- A human-readable reason
- A flag marking whether this was a what-if simulation or a real event

There's a **Recent Maintenance Activity** panel on the dashboard that shows everything from the last ten minutes, refreshing every five seconds. Below it, a **Downloads** panel lets you export the entire history as a CSV (Excel-friendly) or JSON file.

This is the audit trail — the system keeps proof of every action it took on its own and makes it easy to review later.

---

## The chat assistant

In the bottom-right corner of the dashboard there's an "AI Assistant" button. Click it, and a small chat window opens.

Behind the scenes, the chat is **smart about routing**. Most operator questions are simple lookups: "what's the temp of M_3?", "which machine is worst?", "is anything on alert?". For these the assistant doesn't bother with AI at all — it just queries the live data and responds in milliseconds.

But if your question contains "why", "explain", "how", "should I", "cause", "trend" — anything that needs reasoning — it falls through to a small language model running locally on your machine (called `phi3:mini`) which streams the answer word-by-word, like ChatGPT.

This split-brain design keeps the dashboard responsive: simple questions stay fast, hard questions get a thoughtful answer.

**Important:** because the language model runs locally, no question or data ever leaves your computer.

---

## Everything runs on your laptop

This is one of the project's principles: **no cloud dependency.** Everything you've read about — the simulator, the AI models, the workflow engine, the language model, the database — runs on a single machine. The only external requirement is initially downloading the AI model files from the internet (about 2.2 GB), and after that you can yank the network cable and the system keeps working.

Three pieces run inside Docker containers (a tool that packages software so it always behaves the same):
- **n8n** — the workflow engine.
- **Qdrant** — a search database used to look up similar past incidents (for when the chat assistant needs context).
- **Ollama** — the local AI language model service.

Two pieces run directly on your computer:
- **The backend** (the brain that simulates the factory and runs the AI models).
- **The dashboard** (what you see in the browser).

To start everything up: open Docker, run a single command to launch the three containers, then start the backend and the dashboard. Five services in total, all on different ports, talking to each other via standard web requests.

---

## Why this matters (the bigger picture)

Three things make this project interesting for industrial AI:

**1. Predict, don't just react.** Most factory floors react to failures *after* they happen. This system predicts them seconds-to-minutes in advance using a blend of physics, statistics, and graph-based reasoning. By the time a human operator would notice something is off, the system has already started corrective action.

**2. Explainable.** Every prediction comes with a SHAP score (a way to break down which sensor contributed how much to the risk score), a root-cause analysis, and — for serious alerts — a written justification from the language model citing the specific evidence. The system doesn't just say "M_3 is going to fail" — it tells you *why*.

**3. Local and private.** Everything stays on your machine. For factories handling sensitive operational data — automotive, aerospace, defense, pharmaceutical — that's not a nice-to-have, it's a hard requirement.

---

## What's coming next

A few honest limitations worth knowing about:

- **The what-if snapshots live only in memory.** If you restart the backend during an active what-if scenario, you can't revert. Adding a tiny database table to persist them across restarts is a one-line fix.
- **The AI language model has to be downloaded once** (it's 2.2 GB). That's a one-time setup step.
- **The original chain-aware GNN had a bug** where it produced the same answer for every machine — we replaced it with a simpler physics-based version that works correctly. A retrained version would be a future improvement.
- **The chain shape is fixed at four machines in a line.** Branching factories or recirculating loops would need code changes.
- **There's no login screen.** The dashboard is open for anyone on the local network. Fine for a demo, but a real deployment would need authentication.

---

## A short glossary

| Term | What it means |
|---|---|
| **PINN** | Physics-Informed Neural Network. An AI model that learns from physics equations, not just historical data. |
| **GNN** | Graph Neural Network. An AI model designed for connected systems, where one node's data affects its neighbours. |
| **SHAP** | A way to break a prediction down into "this much was the temperature, this much was the vibration..." |
| **n8n** | An open-source workflow engine. Think Zapier, but free and runs on your computer. |
| **Ollama** | A tool for running large language models locally (no cloud). |
| **Docker** | Software that runs other software in isolated boxes called containers. |
| **WebSocket** | A way for the dashboard and backend to stream live data continuously, instead of asking each second. |
| **Tick** | One simulation step. The system runs roughly one tick per second. |
| **Dwell time** | How long a machine has been continuously in Critical state. We trigger auto-maintenance after 10 seconds of dwell. |
| **What-if** | A hypothetical scenario where you fake a machine's state to see how the rest of the plant reacts. Always reversible. |

---

## Where to find more

- The detailed technical report: **PROJECT_REPORT.md** (or `.docx`) — same source, full depth, written for engineers.
- The repository: https://github.com/Siddhi-Karhekar/SynapticFabricfinal
- The architecture notes: `CLAUDE.md` at the repo root.

---

*This guide is intended for a non-technical audience. If you'd like a walkthrough of any specific part in more depth, the technical report has a section index you can jump to.*
