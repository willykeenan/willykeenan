# William Keenan

I'm a developer in New York. I work in banking and build my own projects through KE Studios.

Lately I've been building tools for working with AI coding agents: keeping track of their work, sharing context, and getting them to work together. You'll also find a few apps and research projects below.

<sub>These are personal projects. My views are my own, not my employer's.</sub>

[KE Studios](https://kestudios.dev) · [Agent Rooms](https://agentrooms.io) · [Hugging Face](https://huggingface.co/willykeenan) · [william@kestudios.dev](mailto:william@kestudios.dev)

<table>
<tr><td width="33%" align="center"><a href="https://github.com/willykeenan/ke-activity-monitor"><img src="https://raw.githubusercontent.com/willykeenan/ke-activity-monitor/main/docs/images/agents.png" alt="KE Activity Monitor"></a><br><b>KE Activity Monitor</b></td><td width="33%" align="center"><a href="https://github.com/willykeenan/switchboard"><img src="https://raw.githubusercontent.com/willykeenan/switchboard/main/docs/images/workflow-map.png" alt="Switchboard"></a><br><b>Switchboard</b></td><td width="33%" align="center"><a href="https://github.com/willykeenan/agentbrain-handoffs"><img src="https://raw.githubusercontent.com/willykeenan/agentbrain-handoffs/main/docs/images/handoffs-demo.png" alt="AgentBrain Handoffs"></a><br><b>AgentBrain Handoffs</b></td></tr>
<tr><td width="33%" align="center"><a href="https://github.com/willykeenan/tanpin"><img src="https://raw.githubusercontent.com/willykeenan/tanpin/main/docs/images/dashboard.png" alt="Tanpin"></a><br><b>Tanpin</b></td><td width="33%" align="center"><a href="https://github.com/willykeenan/agentbrain-contextlib"><img src="https://raw.githubusercontent.com/willykeenan/agentbrain-contextlib/main/docs/images/sample-library.png" alt="ContextLib"></a><br><b>ContextLib</b></td><td width="33%" align="center"><a href="https://github.com/willykeenan/live-wire"><img src="https://raw.githubusercontent.com/willykeenan/live-wire/main/docs/images/demo.png" alt="Live Wire"></a><br><b>Live Wire</b></td></tr>
<tr><td width="33%" align="center"><a href="https://github.com/willykeenan/strand-dna"><img src="https://raw.githubusercontent.com/willykeenan/strand-dna/main/docs/images/report.png" alt="Strand DNA"></a><br><b>Strand DNA</b></td><td width="33%" align="center"><a href="https://github.com/willykeenan/dayledger"><img src="https://raw.githubusercontent.com/willykeenan/dayledger/main/docs/images/report.png" alt="DayLedger"></a><br><b>DayLedger</b></td><td width="33%" align="center"><a href="https://github.com/willykeenan/pen"><img src="https://raw.githubusercontent.com/willykeenan/pen/main/docs/images/pen-overlay.png" alt="KE Pen"></a><br><b>KE Pen</b></td></tr>
</table>

## Tools for AI agents

| Project | What it does | Links |
| --- | --- | --- |
| [Switchboard](https://github.com/willykeenan/switchboard) | Organize agents, assign work, and choose which agents can talk to each other. | Hosted version planned for [Agent Rooms](https://agentrooms.io) |
| [AgentBrain Handoffs](https://github.com/willykeenan/agentbrain-handoffs) | Send work to the right agent session and track its progress without interrupting an active turn. | [Demo](https://huggingface.co/spaces/willykeenan/agentbrain-handoffs) |
| [PowerSwarm](https://github.com/willykeenan/powerswarm) | Split a coding job across several AI agents working at once, each on its own branch, and keep only the work that passes its test. | [Recorded run](https://huggingface.co/spaces/willykeenan/powerswarm) |
| [ContextLib](https://github.com/willykeenan/agentbrain-contextlib) | Keep project notes, decisions, and lessons in Markdown, with a log that makes changes traceable. | [Sample library](https://huggingface.co/spaces/willykeenan/contextlib) |
| [KE Activity Monitor](https://github.com/willykeenan/ke-activity-monitor) | See what your agents and their processes are doing on your Mac. | [Product page](https://huggingface.co/spaces/willykeenan/activity-monitor) |
| [CPU and GPU Workers](https://github.com/willykeenan/cpu-gpu-workers) | Check local worker jobs and Apple GPU activity from your coding assistant. | |
| [KE Pen](https://github.com/willykeenan/pen) | Draw on your screen to show an AI assistant what you mean. Free on Mac, Windows, and Linux. | [Download](https://github.com/willykeenan/pen/releases) |
| [DayLedger](https://github.com/willykeenan/dayledger) | Turn Claude Code session logs into a daily report, including work that spans several days. | [Sample report](https://huggingface.co/spaces/willykeenan/dayledger) |
| [Codex Lens](https://github.com/willykeenan/codex-lens) | Browse local Codex conversations. An independent project, not affiliated with OpenAI. | |

## Other projects

| Project | What it does | Links |
| --- | --- | --- |
| [MacroMail](https://github.com/willykeenan/macromail.dev) | Email for AI agents, with an API and MCP server. Free, open source, and self-hosted. | |
| [KE Credits](https://github.com/willykeenan/ke-credits) | Manage prepaid credits, Stripe payments, refunds, and disputes in your own Postgres database. | |
| [Tanpin](https://github.com/willykeenan/tanpin) | Forecast inventory needs, create purchase orders, and track expected deliveries. | [Demo](https://huggingface.co/spaces/willykeenan/tanpin) |
| [Live Wire](https://github.com/willykeenan/live-wire) | An AI-generated satirical news channel with animated anchors. | [Watch](https://livewire.show) |
| [Strand DNA](https://github.com/willykeenan/strand-dna) | Explore a DNA report in your browser. Your raw file stays on your device. | [Sample](https://huggingface.co/spaces/willykeenan/strand-dna) |
| [NY Real Estate Prep](https://github.com/willykeenan/ny-real-estate-prep) | Study for the New York real estate salesperson exam: notes for the full syllabus, 523 practice questions, flashcards, a timed mock exam, and math drills. Free and works offline. | [Use it](https://willykeenan.github.io/ny-real-estate-prep/) |
| [Pointer](https://github.com/willykeenan/pointer-app) | Point at something on your screen, press a key, and ask a question out loud. | |

## Research

### [Waggle + Kea](https://github.com/willykeenan/waggle-kea)

I'm testing ways for agents to exchange structured messages and check what happened to them. Waggle handles the message format; Kea decodes and checks it. Neither gives an agent permission to act.

The repo includes a BANKING77 text-classification benchmark, reproduction instructions, and the results, including experiments that didn't work.

<details>
<summary>A few results</summary>

Adding character features to the word-based baseline improved macro-F1 from **0.8915 to 0.9119**. The paired improvement was **0.0203**, with a 95% bootstrap interval of **[0.0140, 0.0274]**. All 3,050 held-out predictions kept the same routing decisions across direct, JSON, and Waggle/Kea handoffs. Those are results from this benchmark, not a general claim about agent performance.

I also tested reusing a Qwen3-14B prefix state across six branches on Apple Metal. It beat rebuilding the full text after the second branch, but didn't beat the stronger cached-prefix or warmed-native baselines. I published that result too.

</details>

### [Financial Complaint Intelligence](https://github.com/willykeenan/financial-complaint-intelligence)

A comparison of TF-IDF and DistilBERT on public CFPB complaint data, tested on later data with duplicates removed. It also looks at confidence estimates and when a case should go to a person. The simpler baseline won the fixed experiment.

### HEATWAKE

My private research into how market liquidity changes over time. I'm testing whether models can learn useful patterns from order-book events and how those patterns change across time scales.

The models tested so far haven't passed the evaluation criteria I set in advance. I haven't selected a model or established a trading edge.

<details>
<summary>What I'm testing</summary>

HEATWAKE keeps the original order-book events alongside a time-and-price representation built from them. The models use only information available at each prediction time. I'm comparing event-based, visual, and combined approaches.

I call the experimental model family a Liquidity Cognition Model, or LCM. The question is whether it can distinguish what happens next: a large order holding, being withdrawn, absorbing trades, breaking, or reforming.

Tests use chronological splits, strong baselines, checks for future-data leakage, and realistic costs. Forecast accuracy and uncertainty are measured separately. A model that misses any required criterion isn't selected, and a forecast never grants permission to trade.

</details>
