# 参赛材料重建与签字页替换

这是材料制作工具，不属于核心仿真运行依赖。程序离线演示仍按项目README启动。现有材料可以直接阅读，不需要重建。

报告生成器读取保存的 `results/sites_v1` 和历史 `results/safety`，正文包含2026年10月18日冻结追加样本的明确数值。若修改实验数据，应先核对生成器的文字主张，不能只重画图。

V0.7第二轮由`diagnosis_materials.py`增量加入决策诊断，并读取`results/decision_v07_round2`两地图的诊断JSON。需要保留冻结后的20261040—20261059证据及`docs/参赛验收/第二轮实验协议.json`，不能拿旧样本顶替。原5种子、前轮20种子和旧安全配对继续分别陈述。当前工作台截图固定为`docs/images/site-diagnosis.png`。

## 报告和独立表单

需要Windows仿宋字体、Python的python-docx、reportlab、lxml，以及导出用Microsoft Word。当前核查环境使用Codex配套Python；未调用用户另装LibreOffice。官方模板副本在 `templates/`，原始来源是比赛资料2026年10月17日官网复核目录，赛事官方模板优先于本工具。

在项目根目录运行：

```powershell
python tools/materials/build_report.py
powershell -ExecutionPolicy Bypass -File tools/materials/export_documents.ps1
python tools/materials/build_script.py
python tools/materials/build_report.py
powershell -ExecutionPolicy Bypass -File tools/materials/export_documents.ps1
```

第一次Word导出写入实际分页记录，第二次重建静态目录并重新导出。正文为12pt仿宋，保留官方封面与标志。报告保留完整表单，独立副本另输出。Word转换不是视觉验收，改动后须渲染PDF并检查每页。

图表PDF由生成器读取历史CSV产生；项目自带相应PNG。如改变图表或原始CSV，用Poppler重新渲染图表PDF为同名PNG，然后再次构建报告。请使用可用的 `pdftoppm` 并保持原宽高比例。通用 `render_docx.py` 在本机因缺少捆绑soffice失败，本轮采用隐藏Word COM导出和捆绑Poppler逐页核查，没有使用桌面安装版LibreOffice。

## 可编辑答辩

`build_defense.mjs` 是11页当前候选答辩源，数值表从 `results/sites_v1/study.json` 读取，追加20种子文字与保存结果对应。使用安装的presentations技能及其Artifact Tool进行导出校验，需要设置 `PRESENTATION_SKILL_DIR`、`RUNTIME_PYTHON`、`RUNTIME_NODE_MODULES`，并使Node能解析 `@oai/artifact-tool`。使用Codex依赖加载器取得这些路径，不要把某台电脑的用户目录写入项目。

```powershell
node tools/materials/build_defense.mjs
```

生成的PPTX会经过结构、字体、表格和导入检查，复制为答辩目录的固定候选文件。中间文件在 `.verification/materials_rebuild/`。PNG是内部预览；提交PDF应从最终PPTX重开渲染后生成，或由PowerPoint导出，随后逐页检查。当前已交付PDF是11页最终PPTX重开渲染的静态PDF，未声称已在Microsoft PowerPoint中打开测试。

## 真人签字扫描替换

先由本人核对成员、指导教师和联系方式，更新信息表及封面并完成两遍Word导出。全体成员在完整承诺书上真实手写签字和日期，扫描为一页PDF。工具不生成签名，也不验证签名真实性。

```powershell
python tools/materials/merge_signed_commitment.py `
  --report "参赛材料/主报告/主报告_面向园区末端配送的低空风险仿真与起降场选址系统.pdf" `
  --signed-commitment "你的真实签字扫描.pdf" `
  --output "填写真实作品名称和联系人姓名后的新报告.pdf"
```

工具仅定位并替换唯一的承诺书页，保持总页数，不覆盖输入；输出旁有合并哈希记录。须人工复核签字、日期和完整承诺文本，逐页查看新PDF。数字签名PDF不能使用这个纸质扫描替换工具。替换后的报告才用于后续正式包，本轮无真人签字仍是候选材料。
