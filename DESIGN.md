# Dashboard Visual System

<!-- impeccable:design-schema 1 -->

## Direction Contract

**THESIS:** 把看板做成一张“当班经营台账”：数字先给结论，趋势和商品表提供证据，拒绝营销首页和装饰性卡片堆叠。

**OWN-WORLD:** 以米白纸张、墨黑文字和朱砂红数据标记构成的餐饮运营账本；细线、表格规则和等宽数字表达可核对性，暖灰区域承载筛选与审计信息。

**STORY:** 运营人员打开页面先知道当前范围的净营业额、订单和客单价，再沿折线判断每天节奏，最后在商品表定位贡献最高的品项；需要时展开数据质量摘要核对异常。

**FIRST VIEWPORT:** 顶部窄导航与页面标题并列，标题右侧是日期范围筛选；其下是一条横向指标带，首屏下半部直接露出趋势图和 Top 商品表的表头，不把主要信息藏在卡片或弹窗里。

**FORM:** Operate 模式的单页经营台账，采用连续纵向工作区和左右证据栏；在无既有视觉系统的前提下，使用 restrained palette（中性底色 + 朱砂红强调）保持长时间阅读舒适。

## Tokens

- Background: `#F5F2EC`
- Surface: `#FCFBF8`
- Ink: `#1D2421`
- Muted: `#68716B`
- Rule: `#D8D4CB`
- Accent: `#D94F3D`
- Positive: `#2F7A5B`
- Type: system sans with tabular numerals for metrics

## Interaction Rules

- 日期筛选通过显式提交触发一次请求；请求中保留上一次数据并显示加载态。
- 错误状态给出可读原因与重试动作；空范围保留图表和表格骨架但明确说明无数据。
- 数据质量放在原生 `details` 折叠区，不与三项核心指标争夺层级。
- 颜色不单独承担语义，表格和图表同时提供文字标签。
