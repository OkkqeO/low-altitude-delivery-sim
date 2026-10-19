# 官方主报告模板执行合同

参考文件：C:\Users\20115\Desktop\操作系统原理\低空配送仿真Python版\tools\materials\templates\中国仿真创新应用大赛作品方案模板.docx
SHA-256：552e5c9ebe6d0054f395eefef5c1b33a72f825ba16ea40adfae96b3468d78929
参考渲染：C:\Users\20115\Desktop\操作系统原理\低空配送仿真Python版\tools\materials\official-template.pdf，4页；第4页为空白页，仅保留重复页眉。
单节A4纵向，21.00086 × 29.70036 cm；上下2.54 cm，左右3.175 cm；版心14.65086 cm。
源页眉含SIAC标志，每页重复。保留页眉、图片、关系、主题、字体表、编号定义和customXml，不重建。

## 槽位与结构
document.xml/body/p[1:18]为封面；p[3]赛事名称、p[4]赛道、p[5]方向、p[10:13]项目及个人字段、p[17]组委会。
封面赛事名称20pt宋体加粗，方向16pt宋体加粗，字段12pt仿宋；新增项目名称允许两行，空白间隔可按容量调整，个人信息全部留空。
后续源章节槽：摘要、引言、研究背景及意义、研究内容与方案、特色与创新之处、总结、参考文献，按此顺序填充并扩展子章节。
删除源的空参考文献页、尾部空白页及占位换页；保留唯一sectPr。
按官方指南，主报告保留封皮、完整作品信息表、官方诚信承诺书和作品正文；另输出独立表单副本。未知个人信息、成果勾选和迭代状态留空，签字页仍待真人签署替换。
新增目录和附录，便于审阅代码、复现及AI辅助说明；目录仅收集一级章节，页码以Word分页结果生成静态条目并复核。

## 排版约定
依官网正文要求：12pt仿宋，黑色，1.25倍行距，首行2字符；关闭正文段落网格吸附，防止两倍网格行距。标题保留宋体14pt黑色加粗样式，标题不添加横线。
表格使用12pt仿宋、自动行高、浅灰边框、浅灰表头、重复表头、行不拆分；列宽按字段容量设定，不缩小正文。
截图及统计图按版心宽插入，图题12pt仿宋。图例与坐标在图内使用可读字体。
有意新增页脚页码字段；无正文页眉文字，保留原标志。封面与正文共用源节。

## 包保留清单
完整源部件及哈希记录在reference-package.json。
可编辑：word/document.xml、word/styles.xml、word/settings.xml、word/_rels/document.xml.rels、[Content_Types].xml、docProps/core.xml及新增图片/页脚。
其余现有部件均逐字节保留，尤其word/header1.xml及其关系、word/media/image1.png、word/numbering.xml、customXml。
最终验收：源哈希不变；版心与节数不变；所有最终页渲染检查；目录页码及页脚正确；无裁切、表格拆行、空白页。
渲染例外：技能默认render_docx.py已尝试，因包内无soffice.exe失败；采用独立隐藏Microsoft Word 16 COM导出PDF，再由捆绑Poppler渲染逐页检查。
