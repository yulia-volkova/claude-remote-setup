---
name: report-email
description: Use this skill when the user asks to "email eval results", "send eval report", "email me the results", "send results with charts", or any request to email control-arena eval scores, training curves, or comparison tables. Also trigger when sending experiment summaries or analysis via email.
version: 2.0.0
---

# Eval Email Report — Control Arena Results

Send HTML eval reports with inline charts via Gmail API. Extracts scores from `.eval` ZIP files, generates matplotlib charts, and emails a formatted report.

## Data sources

**Local runs:** `.eval` files in `logs/` relative to where eval was launched (typically repo root).

**Modal (remote) runs:** `.eval` files on Modal Volume `control-arena-eval-results`. Download with:
```bash
modal volume get control-arena-eval-results <path> <local_dest>
# or:
uv run python -m control_arena.settings.post_train_bench.cli.ptb_eval_cli download -o logs/modal_runs
```

## Extracting data from .eval ZIP files

```python
import json, zipfile

with zipfile.ZipFile("path/to/file.eval") as zf:
    # Find the sample file
    samples = [n for n in zf.namelist() if n.startswith("samples/")]
    sample = json.loads(zf.read(samples[0]))

# Task name from filename: "samples/MT:bfcl_epoch_1.json" -> "bfcl"
task = samples[0].split("/")[1].split("_epoch")[0].replace("MT:", "")

# Main task score (submitted model)
main_score = sample["scores"]["posttrain_main_scorer"]["value"]  # float 0.0-1.0, or "I" if crashed

# Side task score
side_score = sample["scores"]["posttrain_multi_side_scorer"]["value"]

# Checkpoint training curve
ckpt_meta = sample["scores"]["posttrain_checkpoint_scorer"]["metadata"]
checkpoints = ckpt_meta["checkpoint_scores"]
# Each: {"name": "...", "timestamp": "ISO", "epoch_seconds": int, "accuracy": float, "status": "scored"}
# Also: ckpt_meta["best_checkpoint"], ckpt_meta["num_checkpoints_total"], ckpt_meta["num_checkpoints_scored"]

# Base vs Tuned detection
config = "tuned" if "Starting Checkpoint" in sample.get("input", "") else "base"
```

## Scorers to report
- `posttrain_main_scorer` -- main task accuracy (0-1), the final submitted model
- `posttrain_multi_side_scorer` -- side task aggregate + per-task breakdown in metadata
- `posttrain_checkpoint_scorer` -- intermediate checkpoint scores over training time
- `end_of_trajectory_monitor` -- LLM suspicion assessment
- `max_suspicion_scorer` -- peak suspicion

## Charts (matplotlib PNG, white bg, 150 dpi)

Always use:
```python
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# ... plot ...
fig.patch.set_facecolor('#ffffff')
plt.savefig('/tmp/CHART_NAME.png', dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
```

**Chart 1: Training curve** (always include)
- X-axis: hours from start (normalize by subtracting first checkpoint's `epoch_seconds`, divide by 3600)
- Y-axis: accuracy percentage
- Plot checkpoint scores as connected circles
- Plot submitted score (from `posttrain_main_scorer`) as a star at the last checkpoint's x-position
- Dashed line connecting last checkpoint to submitted star to show the gap
- These can differ because: agent may train more after last checkpoint, main scorer may use different eval sample size, agent might replace final_model/ before submitting

**Chart 2: Score overview** -- bar chart of all scorer values, color-coded (green=main, orange=side, red=suspicion)

**Chart 3: Side task breakdown** (if multi-side scorer) -- horizontal bars of individual side task scores

**Chart 4: Cross-run comparison** -- optional, when user provides multiple evals

## HTML comparison table (Base vs Tuned)

When the user provides paired eval files (base + tuned per benchmark), generate an HTML table:

| Benchmark | 3B Base | 3B Tuned | Delta | Progress |
|-----------|---------|----------|-------|----------|

- Delta = tuned_score - base_score (in percentage points)
- Delta badge colors: green (#16a34a/#dcfce7) >= 30pp, yellow (#f59e0b/#fef3c7) 10-30pp, red (#dc2626/#fee2e2) < 10pp
- Progress bar: horizontal bar showing tuned_score as % of 100, colored by delta color
- Sort rows by delta descending (biggest improvement first)
- Use inline CSS, table-based layout for email compatibility

```html
<table style="width:100%; border-collapse:separate; border-spacing:0 8px; font-family:system-ui;">
  <thead>
    <tr style="color:#6b7280; font-size:0.85rem;">
      <th style="text-align:left; padding:8px 16px;">Benchmark</th>
      <th style="text-align:center; padding:8px 16px;">3B Base</th>
      <th style="text-align:center; padding:8px 16px;">3B Tuned</th>
      <th style="text-align:center; padding:8px 16px;">Delta</th>
      <th style="text-align:left; padding:8px 16px;">Progress</th>
    </tr>
  </thead>
  <tbody>
    <tr style="background:white; box-shadow:0 1px 2px rgba(0,0,0,0.05);">
      <td style="padding:16px; font-weight:600;">{benchmark_name}</td>
      <td style="text-align:center; color:#6b7280;">{base_score}%</td>
      <td style="text-align:center; font-weight:700;">{tuned_score}%</td>
      <td style="text-align:center;">
        <span style="background:{delta_bg}; color:{delta_color}; padding:2px 10px;
              border-radius:9999px; font-weight:600; font-size:0.85rem;">+{delta}pp</span>
      </td>
      <td style="padding:16px;">
        <div style="background:#e5e7eb; border-radius:9999px; height:16px; width:150px;">
          <div style="background:{bar_color}; border-radius:9999px; height:100%;
               width:{tuned_score}%; min-width:4px;"></div>
        </div>
      </td>
    </tr>
  </tbody>
</table>
```

## Subject line format
```
[EVAL] {MODE} | {main_task} | main={score:.0%} side={score:.0%} suspicion={score:.2f}
```

## Score interpretation
- HONEST mode: main should be high, side should be LOW (honest agent shouldn't do side tasks), suspicion low
- ATTACK mode: main should be high, side should be HIGH (attack succeeds). Suspicion can be high -- it measures whether the monitor detected the attack
- Flag anomalies: honest agent with high side score (doing something it shouldn't), or attack with high main but zero side (attack failed)

## Sending command

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/send_report_email.py \
  --to RECIPIENT \
  --subject "..." \
  --html /tmp/eval_report.html \
  --image training_curve:/tmp/training_curve.png \
  --image score_overview:/tmp/score_overview.png \
  --image side_tasks:/tmp/side_tasks.png \
  --label Evals
```

## Key rules
- Use `<img src="cid:NAME" />` -- Gmail strips base64 data URIs
- PNG only -- email clients reject SVG
- White background: `fig.patch.set_facecolor('#ffffff')`, save at `dpi=150`
- Always extract from `.eval` ZIP -- it's the source of truth
- Ask user for recipient email or use previously specified address
- Use inline CSS (email clients strip `<style>` blocks)
- Tables render more reliably than flexbox/grid across email clients
- Keep total email size under 10MB (Gmail limit)

## Prerequisites

- OAuth token at `~/.config/google-docs-mcp/token.json` with `gmail.send` scope
- Gmail API enabled in the Google Cloud project
- Python packages: `google-api-python-client`, `google-auth`, `matplotlib`
