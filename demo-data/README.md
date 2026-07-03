# Demo Data

Sample artifacts used by the demo simulator and dashboard views.

At bootstrap stage this folder contains only structure and metadata
placeholders. Real fixed-width CCD files, FedACH settlement files, NACHA
return files, and historical records are added in later prompts.

## Layout

```text
demo-data/
  ccd/           CCD upload files (fixed-width)
  settlement/    FedACH settlement reports
  returns/       NACHA return files
  historical/    Historical payment records for risk analysis
  scenarios/     End-to-end demo scenarios (JSON manifests)
  local-folder-demo/
    batch_1100/  Seed artifacts copied into backend/demo-inbox in phases
```

Runtime state produced by the simulator lives under `demo-data/runtime/` and
is gitignored.

See [../docs/demo-scenarios.md](../docs/demo-scenarios.md) for the demo
storylines and cycle configuration guidance.
