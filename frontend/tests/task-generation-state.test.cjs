const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");
const vm = require("node:vm");
const typesSource = fs.readFileSync(path.join(__dirname, "../src/lib/types.ts"), "utf8");
const typesOutput = ts.transpileModule(typesSource, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const typesContext = { exports: {} };
vm.runInNewContext(typesOutput, typesContext);
const uiConstantsSource = fs.readFileSync(path.join(__dirname, "../src/lib/ui-constants.ts"), "utf8");
const uiConstantsOutput = ts.transpileModule(uiConstantsSource, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const uiConstantsContext = {
  exports: {},
  require: (moduleName) => {
    if (moduleName === "@/lib/types") return typesContext.exports;
    throw new Error(`Unexpected test import: ${moduleName}`);
  },
};
vm.runInNewContext(uiConstantsOutput, uiConstantsContext);
const source = fs.readFileSync(path.join(__dirname, "../src/lib/task-generation-state.ts"), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const context = {
  exports: {},
  require: (moduleName) => {
    if (moduleName === "@/lib/ui-constants") return uiConstantsContext.exports;
    throw new Error(`Unexpected test import: ${moduleName}`);
  },
};
vm.runInNewContext(output, context);
const { generationStatus, isGenerationLifecycleEvent, resolveSceneAssetRefreshAction } = context.exports;

test("publication failures and jobs do not replace completed generation status", () => {
  assert.equal(generationStatus({ status: "completed", active_job: { job_type: "publish", status: "running" } }), "completed");
  assert.equal(generationStatus({ status: "failed", active_job: { job_type: "full_pipeline", status: "completed" } }), "completed");
});
test("new queued job replaces old failure and terminal job stops stale live running", () => {
  assert.equal(generationStatus({ status: "failed", active_job: { job_type: "full_pipeline", status: "queued" } }), "pending");
  assert.equal(generationStatus({ status: "running", active_job: { job_type: "full_pipeline", status: "cancelled" } }, "running"), "cancelled");
});
test("individual asset, scene and preview updates do not start a generation workflow", () => {
  for (const event of ["asset.created", "scene.status_changed", "video.preview_ready", "research.warning"]) {
    assert.equal(isGenerationLifecycleEvent(event), false);
  }
  assert.equal(isGenerationLifecycleEvent("job.started"), true);
  assert.equal(isGenerationLifecycleEvent("task.failed"), true);
  assert.equal(isGenerationLifecycleEvent("task_failed"), false);
});

test("online assets use the same workflow-unit refresh contract", () => {
  assert.equal(resolveSceneAssetRefreshAction("online_asset", true, true), "workflow_unit");
  assert.equal(resolveSceneAssetRefreshAction("generated_image", true, true), "workflow_unit");
  assert.equal(resolveSceneAssetRefreshAction("generated_video", true, true), "workflow_unit");
  assert.equal(resolveSceneAssetRefreshAction("online_asset", false, true), "none");
});
