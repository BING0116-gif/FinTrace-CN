# FinTrace-CN 面试 Demo 指南

## 准备

~~~powershell
python scripts/bootstrap_demo.py
python -m streamlit run workbench.py
~~~

演示数据由本地确定性生成器创建，provider 为 illustrative_fixture，data_quality 为 illustrative_demo_not_for_investment，不代表真实价格或财报。

## 60 秒演示路线

1. 打开“案例演示”，选择贵州茅台 illustrative 成功案例；
2. 在“研究总览”指出快照 ID、研究截止时间、Provider 和 Validator；
3. 在“证据与校验”展示价格 × 总股本 → 市值的 Evidence DAG；
4. 在“同行估值”展示同一行业、同一时点的 PE/PB/PS 与 IQR 处理；
5. 返回阻断案例，说明缺少总股本时系统隐藏估值，而不是让模型补数字；
6. 打开“每日复盘”，强调 synthetic_demo 永不冒充实时行情。

## 面试口径

- 成功案例表示证据与规则允许输出，不代表值得买入；
- warning 可以允许输出，但必须展示陈旧或覆盖不足；
- blocked 必须隐藏确定性结论；
- dry-run 消融只验证机制，真实模型指标需单独运行；
- 本项目基于开源项目二次开发，应主动说明继承与新增边界。
