# How ExpressNode was built

ExpressNode began as **Coding Nodes**. It was later called Expression Nodes, and then ExpressNode.
It was built milestone by milestone, each one leaving something that worked and was tested.

| Milestone | What it added |
|---|---|
| M1 | Frontend: a Python-subset parser that turns a function into a typed graph (the EvalGraph IR) |
| M2 | Grouping: each user function becomes its own named node group, so the output reads like the code |
| M3 | Backend: operation emitters, an emission plan, and an executor that builds the Geometry Nodes tree |
| M4 | The Expression Node Group (drop a compiled group into any tree) |
| M5 | Polish: apply modes, keeping tuned values on recompile, error messages, packaging |
| M6 | A numpy reference evaluator: the oracle that proves the maths is right |
| M7 | OSL backend (Cycles) |
| M8 | GLSL backend (Blender's GPU module) |
| M9 | WGSL backend (WebGPU compute) |

The intermediate representation came from an earlier procedural-geometry engine and was vendored
into `expressnode/_ir`, so ExpressNode is self-contained.

## Verification in Blender

- **2026-09-27:** every planned Blender check was automated (`tests/blender/`, `tests/gpu/`) and
  run on Blender 5.0.1 and 5.1.2. The first real run found and fixed many bugs:
  - the Geometry Nodes executor wired sockets wrongly
  - most OSL didn't compile
  - noise didn't match between backends
  - several operations computed the wrong thing

  The checklist those checks came from is in [design/TESTING-CHECKLIST.md](design/TESTING-CHECKLIST.md).
- **2026-10-07:** Blender 5.2 moved Geometry Nodes modifier inputs from ID properties to RNA, and
  ExpressNode now handles both. 411 of 411 checks passed on 5.0.1, 5.1.2 and 5.2.2 (Linux, Vulkan),
  WebGPU included.
- **2026-10-08:** renamed the package `coding_nodes` → `expressnode`, made it a Blender extension
  (0.9.0), and added migration for files from the old add-on. 426 of 426 Blender and GPU checks
  passed on 5.0.1, 5.1.2 and 5.2.2 (Windows).
