# 带货轮播设计规范

由当前 Agent 直接阅读商品信息、查看参考图并运用本规范，不需要再调用分析服务。

## 从真实商品信息到销售叙事

- 先明确商品是什么、谁在什么场景需要它，以及有什么可证实的购买理由。
- 首图用具体、简短、有事实依据的利益点或问题吸引停留，不做虚构的恐吓和夸大承诺。
- 中间每页只讲一件事：使用场景、单个卖点、真实细节、操作步骤或购买疑虑。证据只来自用户资料或能实际看见的外观，不能杜撰用户评价和测试效果。
- 尾图总结购买理由并给出适度行动引导。用户没提供价格、折扣、库存和链接时，避免限时低价、快售罄和具体购买链接。
- 国家确定默认语言，实际受众和用户要求确定语气。不要把“马来西亚”等国家标签自动等同于宗教认证、人群价值观或某种消费偏好。

## 整套视觉一致性

先定一套共享方向，再写逐页提示词：

- 商品外观锚点：轮廓、尺寸关系、颜色、包装、盖子、按键、数量，依据已查看参考图。
- 颜色系统：背景色、正文色、强调色，兼顾商品识别与阅读对比。
- 排版：标题与正文的字体风格、层级、对齐、常用位置，避免六张六种字体。
- 光线与场景：统一质感，允许各页因销售任务切换场景和景别。
- 文字：标题短，正文只讲一个要点；按目标语言自然书写，避免把整段商品描述塞到图上。

默认采用3:4竖图，具体尺寸使用生图工具支持的值。文字与商品关键细节避开边缘和可能的播放器覆盖区。安全边距按画幅和当前发布场景调整，不把固定百分比当作平台官方要求。不要通过后期裁切实现比例而切掉文字或包装。

## 每张完整提示词

提示词是一份直接可执行的自然语言成品设计简报，每份都应包含完整上下文，即使只单独重生这一张也能保持方向。

1. 输出目标：TikTok 电商轮播第几页、该页的信息任务、构图比例。
2. 商品与参考：选用哪些已提供参考，保留哪些可见外观特征。
3. 主体布局：位置、占画比例、景别、场景、道具、光线与质感。
4. 共享风格：明确配色和字体，承接整套方向。
5. 准确图中文字：逐字引用已定稿的目标语言标题和正文。
6. 文字渲染：显著大标题、精简小正文、高对比、避遮挡、可读留白；由生图模型直接绘制。
7. 约束：不添加未指定的促销、认证或参数；可以保留参考图真实包装文字和Logo，不能编造。

### 结构示例（必须替换占位符后才能生图）

> Create a finished vertical 3:4 TikTok product carousel image for [market], page [position], focused on [one supported benefit]. Use the supplied product references to preserve [observed shape, color, packaging and parts]. Place the product [specific composition] in [scene] with [lighting]. Follow the series palette [colors] and typography [font style]. Render EXACT text directly in the image: headline "[approved target-language title]"; supporting copy "[approved target-language body]". Make the headline prominent and the supporting copy concise, with strong text/background contrast and clear mobile-safe spacing. Keep text clear of the product and likely interface overlays. Preserve authentic reference branding; add no extra text, invented specifications or certification badges.

不得将商品字典、Markdown表格、原始长描述或一串字段直接传入生图工具。对工具返回的图片必须实际检查；写了“EXACT”并不证明模型已经拼写正确。

## 单图改动与验收

- 改画面时锁定现有文案；改文字时使用用户明确的新文案，并重新生成完整设计简报。
- 重生时保留原商品参考与整套方向；工具支持定向编辑时可附当前图片，但不能牺牲商品识别。
- 看图核对商品是否变形/换款/少配件、文案是否漏字/乱码/越界、销售参数是否准确、风格是否一致。
- 文件存在与视觉验收是两个独立状态。不能看图时只标文件已收到，不宣称视觉合格；外语表达不确定时明确标待复核。
- 已完成图片不因某张失败被重新生成；改动成功后才切换当前选中版本。
