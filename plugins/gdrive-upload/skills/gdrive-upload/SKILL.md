---
name: gdrive-upload
description: Use this skill when the user asks to "upload to Drive", "save to Google Drive", "upload eval to Drive", "put this on Drive", "share via Drive", or any request to upload files (especially .eval files) to Google Drive.
version: 1.0.0
---

# Google Drive Upload

Upload files to Google Drive via the Drive API.

## Naming convention

Use comprehensive, descriptive names so files are identifiable without opening them:

```
{task}_{mode}_{compute}_{duration}_{model}_{date}.eval
```

- **task**: benchmark name (bfcl, cybench, etc.)
- **mode**: attack or honest
- **compute**: how it was run -- `tinker-tool` or `gpu`
- **duration**: training/run duration (3h, 6h, etc.)
- **model**: model config (3b-base, 3b-tuned, etc.)
- **date**: ISO date

Examples:
- `bfcl_attack_gpu_3h_3b-tuned_2026-04-15.eval`
- `cybench_honest_tinker-tool_6h_3b-base_2026-04-15.eval`
- `bfcl_attack_gpu_3h_vs_honest_comparison_2026-04-15.eval`

Extract these components from the `.eval` file:

```python
import json, zipfile

with zipfile.ZipFile("path/to/file.eval") as zf:
    samples = [n for n in zf.namelist() if n.startswith("samples/")]
    sample = json.loads(zf.read(samples[0]))

# Task name from filename: "samples/MT:bfcl_epoch_1.json" -> "bfcl"
task = samples[0].split("/")[1].split("_epoch")[0].replace("MT:", "")

# Base vs Tuned
config = "tuned" if "Starting Checkpoint" in sample.get("input", "") else "base"
```

Always ask the user for the mode (attack/honest) if it's not obvious from context.

## Upload command

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/upload_to_gdrive.py FILE [FILE ...] \
  --folder FOLDER_ID \
  --name "descriptive_name.eval"
```

### Arguments
- `FILE` -- one or more file paths to upload
- `--folder FOLDER_ID` -- Google Drive folder ID (from the folder URL: `drive.google.com/drive/folders/FOLDER_ID`)
- `--name NAME` -- override filename in Drive (single file only)

### Examples

Single file:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/upload_to_gdrive.py \
  logs/my_eval.eval \
  --folder 1abc123def456 \
  --name "bfcl_attack_3b-tuned_2026-04-15.eval"
```

Multiple files:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/upload_to_gdrive.py \
  logs/eval1.eval logs/eval2.eval \
  --folder 1abc123def456
```

## Key rules
- Always use descriptive names following the naming convention above
- Ask the user for the Drive folder ID if not previously specified
- Ask the user for mode (attack/honest) if ambiguous
- The script prints the Drive link after upload -- always show this to the user
- `.eval` files are ZIP archives -- upload as-is, don't extract

## Prerequisites
- OAuth token at `~/.config/google-docs-mcp/token.json` with `drive.file` scope
- Google Drive API enabled in the Google Cloud project
- Python packages: `google-api-python-client`, `google-auth`
