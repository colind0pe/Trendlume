# Knowledge Production Mode

Trendlume 当前的 topic、fixed script 和 Trend→Video 入口都归属于 Knowledge Mode。Trend 仍然只是一个输入源，不是另一种生产模式；省略 `production_mode` 时按项目默认或 Knowledge 处理。当前运行时契约使用 `KnowledgeBrief`，不再保留 `content_brief` 入口；旧数据库记录只在迁移过程中被规范化。

## 从主题到知识视频

Knowledge Task 的编辑核心是四个问题：

1. 这条视频面向谁（`audience`）？
2. 希望观众理解的核心主张是什么（`thesis`）？
3. 观众看完应该带走什么（`viewer_takeaway`）？
4. 哪些关键主张需要来源支持（`key_claims` / `source_refs`）？

`genre` 仍然可用于科普、历史、商业等表达方向，但它是 Knowledge Brief 内部的内容方向，不再被用户当作全局生产模式选择。

## KnowledgeBrief

后端结构化契约如下：

```json
{
  "audience": "第一次接触这个主题的普通观众",
  "thesis": "每个关键结论都应能回到来源",
  "viewer_takeaway": "看完知道如何复核结论",
  "key_claims": [
    {
      "id": "claim-1",
      "statement": "来源关系应保留到分镜",
      "source_refs": ["source-a1b2c3"]
    }
  ],
  "source_refs": ["source-a1b2c3"],
  "genre": "science_tech"
}
```

有效基线升级时，迁移脚本会把旧数据库中的 `ContentBrief` 结构转换为 `KnowledgeBrief`；迁移完成后的 API、Task payload 和 UI 只使用当前字段。

## 来源与视觉逻辑

联网研究结果中的来源会获得稳定的 `ref_id`。脚本和分镜使用这些 ID 关联主张与来源，生成时会清理不在当前研究快照中的引用。没有联网快照时，显式手工来源仍可保留，但不会被伪装成已验证的在线资料。

每个 Scene 独立保存：

- `visual_role`：`concept`、`process`、`comparison`、`timeline`、`data`、`example`、`quote`、`b_roll`；
- `claim_refs`：本镜头解释的主张 ID；
- `source_refs`：本镜头展示或依赖的来源 ID；
- `production_metadata`：知识模式的阅读顺序、卡片或图表等制作元数据。

这些字段与 `layout_params` 分离。`layout_params` 继续承担模板和渲染兼容参数，知识语义不再塞入排版参数。

视觉角色的含义是信息逻辑，而不是装饰标签：例如 `process` 应表现步骤或因果链，`comparison` 应明确并列差异，`data` 应优先保证数字和趋势可读，`b_roll` 只补充语境而不承载新的关键结论。

## UI 与基础设施边界

项目创建入口使用 `KnowledgeTaskForm`。主题、受众、主张、观众带走什么和来源核验是默认输入；镜头数量、开场表达、视觉风格、画面来源、模板、工作流和自动发布位于高级设置。

Trend Center 会默认创建 Knowledge Task，并把热点快照作为 `trend_provenance` 保存。已有 Assets、TTS、字幕、渲染、发布和 Provider 抽象保持共用；本次变更没有新增渲染器或 Provider 层。

## QA 边界

提示词离线评估覆盖 KnowledgeBrief 完整性、主张/来源闭包和视觉角色合法性。数据库迁移与 Scene API 测试覆盖新字段的默认值和持久化契约。

最终 MP4 的字幕遮挡、画面可读性、素材真实性和外部 Provider 的实际授权仍需要按部署环境做人工或 live QA；离线 fixture、mock Provider 和单元测试不等于真实检索、ComfyUI 或发布平台验证。
