"""Create the competition main report from retained official template and saved data."""
from pathlib import Path
from copy import deepcopy
import csv, hashlib, json, re, shutil, sys
from zipfile import ZipFile, ZIP_DEFLATED
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, Color, white, black

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'engine.py').is_file())
QA = Path(__file__).resolve().parent
OFFICIAL = Path(__file__).resolve().parent / 'templates'
REF = OFFICIAL / '中国仿真创新应用大赛作品方案模板.docx'
OUT = ROOT / '参赛材料/主报告'
OUT.mkdir(parents=True, exist_ok=True)
FIG = OUT / '图表'
FIG.mkdir(exist_ok=True)
TITLE = '面向园区末端配送的低空风险仿真与起降场选址系统'
STEM = '主报告_' + TITLE
DOCX = OUT / (STEM + '.docx')
MD = OUT / (STEM + '.md')
SUMMARY = list(csv.DictReader((ROOT/'results/safety/summary.csv').open(encoding='utf-8-sig')))
RAW = list(csv.DictReader((ROOT/'results/safety/raw_metrics.csv').open(encoding='utf-8-sig')))
IDX = {(r['scenario'], r['plan'], r['dispatch']):r for r in SUMMARY}
SCENARIOS = [('normal','正常配送'),('peak','高峰订单'),('closure','局部空域关闭')]
PLANS = [('fixed','固定布局'),('distance','距离优先'),('combined','综合风险')]
def val(s,p,d,m): return float(IDX[s,p,d][m+'_mean'])
def sd(s,p,d,m): return float(IDX[s,p,d][m+'_std'])
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

# Capture the original package contract; opaque parts are restored byte-for-byte.
with ZipFile(REF) as z:
    inventory = [{'path':i.filename,'size':i.file_size,'sha256':hashlib.sha256(z.read(i.filename)).hexdigest()} for i in z.infolist() if not i.is_dir()]
    source_parts = {i['path']:z.read(i['path']) for i in inventory}
(QA/'reference-package.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
artifact = f'''# 官方主报告模板执行合同

参考文件：{REF}
SHA-256：{sha(REF)}
参考渲染：{QA / 'official-template.pdf'}，4页；第4页为空白页，仅保留重复页眉。
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
'''
(QA/'artifact.md').write_text(artifact,encoding='utf-8')

pdfmetrics.registerFont(TTFont('FangSong',str(Path(__import__('os').environ.get('WINDIR','C:/Windows'))/'Fonts/simfang.ttf')))
pdfmetrics.registerFont(TTFont('YaHei',str(Path(__import__('os').environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc')))
def text(c,x,y,t,size=14,font='YaHei',color=black,align='left'):
    c.setFillColor(color); c.setFont(font,size)
    getattr(c, {'left':'drawString','center':'drawCentredString','right':'drawRightString'}[align])(x,y,str(t))
def box(c,x,y,w,h,lines):
    c.setStrokeColor(HexColor('#8795a5')); c.setFillColor(HexColor('#f3f6f9')); c.roundRect(x,y,w,h,6,fill=1,stroke=1)
    for i,t in enumerate(lines): text(c,x+w/2,y+h/2+(len(lines)-1)*10-i*20,t,14,align='center')
def arrow(c,x1,y1,x2,y2):
    c.setStrokeColor(HexColor('#45566b')); c.setLineWidth(1.3); c.line(x1,y1,x2,y2)
    import math
    a=math.atan2(y2-y1,x2-x1)
    for d in [-.45,.45]: c.line(x2,y2,x2-8*math.cos(a+d),y2-8*math.sin(a+d))

def architecture():
    p=FIG/'系统流程.pdf'; c=canvas.Canvas(str(p),pagesize=(600,310))
    box(c,10,210,170,70,['地图输入','图片  Excel  JSON'])
    box(c,215,210,170,70,['人工确认与组件编辑','尺度  楼高  业务点位'])
    box(c,420,210,170,70,['场景与风险建模','障碍栅格  人群热点'])
    arrow(c,180,245,215,245); arrow(c,385,245,420,245)
    box(c,420,85,170,70,['风险加权 A*','场站到配送点航路'])
    box(c,215,85,170,70,['两场站枚举与评分','独立设计订单选址'])
    box(c,10,85,170,70,['任务预约与错峰','连续时间间距审计'])
    arrow(c,505,210,505,155); arrow(c,420,120,385,120); arrow(c,215,120,180,120)
    text(c,300,36,'输出：方案对比、轨迹回放、任务与冲突明细、批量统计',14,align='center')
    c.showPage(); c.save()

def chart(metric,title,ylabel,filename,maximum,factor=1):
    p=FIG/(filename+'.pdf'); c=canvas.Canvas(str(p),pagesize=(600,350))
    x0,y0,w,h=62,70,510,220
    text(c,20,325,title,17)
    text(c,62,301,ylabel,12)
    c.setLineWidth(.5)
    for tick in range(6):
        y=y0+h*tick/5; c.setStrokeColor(HexColor('#e0e5eb')); c.line(x0,y,x0+w,y)
        text(c,x0-8,y-4,f'{maximum*tick/5:g}',11,align='right')
    colors=[HexColor('#8b9db3'),HexColor('#087f8c')]
    for j,(s,label) in enumerate(SCENARIOS):
        center=x0+w*(j+.5)/3
        for k,d in enumerate(['baseline','staggered']):
            m=val(s,'combined',d,metric)*factor; e=sd(s,'combined',d,metric)*factor
            x=center+(-37 if k==0 else 7); bh=h*m/maximum
            c.setFillColor(colors[k]); c.rect(x,y0,30,bh,stroke=0,fill=1)
            c.setStrokeColor(HexColor('#283c50')); c.setLineWidth(1)
            c.line(x+15,y0+h*max(0,m-e)/maximum,x+15,y0+h*(m+e)/maximum)
            c.line(x+10,y0+h*(m+e)/maximum,x+20,y0+h*(m+e)/maximum)
            text(c,x+15,y0+h*(m+e)/maximum+7,f'{m:.1f}' if metric!='mean_exposure' else f'{m:.3f}',11,align='center')
        text(c,center,45,label,14,align='center')
    for i,label in enumerate(['基线调度','错峰调度']):
        c.setFillColor(colors[i]); c.rect(343+i*110,318,12,12,stroke=0,fill=1)
        text(c,361+i*110,318,label,12)
    text(c,300,13,'综合风险布局；每场景5个评价种子；误差线为样本标准差',11,align='center')
    c.showPage();c.save()

architecture()
chart('air_conflict_count','多机间距不足事件对比','事件数 / 次','间距不足事件',40)
chart('mean_delivery','配送时间与错峰代价','平均配送时间 / 秒','配送时间',1000)
chart('mean_exposure','路径人员暴露代理指数','每单路径暴露指数','人员暴露',1.2)

DESCRIPTION = '面向校园与园区末端配送，开发离线Python桌面仿真系统。支持图片、Excel、JSON导入，米制定标、手动楼高和地图组件编辑。使用风险加权A*、两点组合枚举、任务预约与连续时间间距检测。V0.7以3个设计种子的正常与高峰仿真比较28种布局，再冻结位置用5个独立种子评价固定位置、距离优先和运行优选，支持1—20架无人机。保存30条当前评价记录，并保留历史90条安全配对评价。系统呈现时效与人员暴露权衡，支持回放和结果导出；未开展真实飞行验证。'
INNOVATION = '将米制定标、手动楼高与可编辑地图直接连接航路及选址；在同一位置设计中纳入正常、高峰需求和错峰预约，以失败、超时、时效与暴露的词典序目标评价布局；冻结位置和机队后独立评价，保留不利结果、失败原因与任务级证据。A*和相对运动检测为已有方法，创新定位为决策流程与可审计工程集成。'
VALUE = '可用于园区配送方案前期比较和教学演示，帮助核对候选位置、航路与订单高峰容量。用户修改地图及无人机数量后可重新选址、回放和导出。当前结果来自模拟园区，运行优选并非每项指标最优；应用前仍需核实尺度、楼高、需求、场地和运行规则，并补充能耗、动力学与实地验证。'
assert len(DESCRIPTION)<=300 and len(INNOVATION)<=200 and len(VALUE)<=200

content = []
def H(level,t):content.append(('h',level,t))
def P(t):content.append(('p',t))
def T(caption,headers,rows,widths):content.append(('table',caption,headers,rows,widths))
def I(name,caption):content.append(('image',name,caption))
def E(t):content.append(('equation',t))
def C(t):content.append(('code',t))

H(1,'摘要')
P('园区无人机配送的规划需要同时考虑建筑通行、人群暴露、起降场位置以及多架无人机对场站和空中时隙的竞争。单纯比较最短航程，难以解释同一地图中不同布局的时效与暴露差异。本作品建立固定巡航高度下的研究仿真系统，将地图编辑、风险加权航路、两起降场组合选址、订单分配和错峰预约放入同一计算流程。')
P('系统主体使用Python实现，采用Tkinter提供桌面交互。地图支持图片、Excel和JSON输入；图片只提取建筑候选，用户确认米制尺度并手动填写楼高，随后可在程序内增删、移动和调整四类组件。模型使用八邻域A*搜索风险加权航路，以独立设计订单枚举和评价两个场站的组合；运行阶段选择最早可送达的无人机，并通过连续时间相对运动计算检查间距，必要时推迟起飞。')
P('在960米×640米模拟园区中，对正常、高峰和固定局部空域关闭三种场景，采用5个独立评价种子、3种布局及2种调度，形成90条运行指标和45组配对比较。保存结果中的间距不足事件合计由700次降至0次，两种调度均无失败订单；按45组运行等权计算，平均配送时间增加35.53秒。正常场景的综合风险布局在错峰后每单路径暴露指数为0.849，低于距离优先布局的1.093，但配送时间由123.71秒增加至137.15秒。高峰场景仍存在明显超时，表明错峰不能代替容量扩充。')
P('全部结果来自明确设定的模拟输入。人员暴露是相对代理指标，间距结论只适用于固定高度、匀速折线及悬停模型；本作品尚未完成真实飞行验证。现阶段成果适合方案比较和模型教学，可作为接入经核实园区数据的基础。')
P('关键词：低空配送；风险加权A*；起降场选址；连续时间间距检测；错峰调度；可编辑地图')

H(1,'1 引言')
P('本作品面向校园或园区内的小范围末端配送，研究“选择哪两个候选场站、沿什么航路配送、何时安排各架无人机出发”三个相互影响的问题。项目不把三维画面复杂度作为研究目标，而以可解释的模型、可操作的地图和可复核的对照实验支撑决策。')
P('针对使用者难以整理坐标文件的问题，系统允许直接导入地图图片，再确认尺度和楼高；针对场站位置改变后需要重做航路的问题，系统把地图转换成统一场景对象，自动更新障碍和风险；针对多机只做动画而不检查接近的问题，系统独立审计完整任务航迹，并记录接近时间、最小间距和涉及订单。')
P('报告依次说明需求与范围、数据组织、算法与系统实现、配对实验和应用流程。算法部分采用标准A*思想[1]，本作品的主要工作在于模型组合、编辑交互、预约约束和证据导出。对“最优”的表述限定在给定离散图或有限候选集合内，不声称获得真实城市三维空域的全局最优解。')

H(1,'2 研究背景及意义')
H(2,'2.1 实际问题与评价目标')
P('校园和园区配送具有服务范围相对集中、建筑密集、人员活动区域差异明显的特点。无人机可以缩短部分地面绕行，但直线飞行可能穿过高建筑投影或人群活动区域；候选起降场的距离优势，也可能被返航、起降排队和机队分配抵消。因此需要同时报告时间、航程、路径暴露、准时率、完成率及间距不足事件。')
P('民用无人机优化研究涉及任务分配、航路、设施和作业约束，Otto等[2]对此进行了综述。Murray和Chu[3]研究卡车与无人机协同配送，Dorling等[4]研究无人机配送路径问题；Kong等[5]进一步按协同程度梳理相关模型。本作品选择固定场站服务园区的场景，将车辆协同、补能和多点串行配送留在研究范围之外，以便集中检验选址、路径暴露与错峰之间的关系。')
P('本作品提出三个可用仿真检验的问题：其一，距离优先选址与综合风险选址是否形成可观察的权衡；其二，在相同订单、布局和航路下，错峰能否消除模型中的间距不足，以及付出多少时效代价；其三，订单高峰和固定空域关闭会如何改变方案表现。上述问题均通过保存输入和运行明细回答。')
H(2,'2.2 研究范围与假设')
P('研究空间为本地米制平面，建筑附带高度属性，航路在一个给定巡航高度上搜索。该表示属于带建筑高度约束的二维规划，不包含连续三维机动。无人机按恒定速度沿折线飞行，配送处理和返场排队可发生悬停；每架无人机固定归属一个场站，每个场站只有一个共享起降服务位，任务完成返场服务后才能执行下一单。')
P('建筑高度、尺度、候选场站和人群热点属于输入条件。图片中的楼高不能可靠推断，必须手动录入；人群热点权重为研究设定，没有用未经采集的真实人数代替。20米空中间距、8米建筑平面间距与5米垂直间距均为模型参数，不能直接用作监管或运营标准。')
H(2,'2.3 应用价值与证据要求')
P('系统的直接价值是降低地图试配和方案比较的操作门槛，使用户能够修改一栋建筑的高度、一个场站的位置或一处需求权重，并重新计算其影响。结果保留到订单和航路层级，便于解释“为何绕行”“为何等待”“为何未完成”。真实部署还需补足场地、气象、能耗、定位与运行规则等证据，本报告不据模拟结果推算营业收入或实际事故率。')

H(1,'3 研究内容与方案')
H(2,'3.1 系统结构与数据流程')
P('系统将交互与核心计算分离。地图编辑器负责输入和校验；仿真引擎根据统一场景建立栅格和航路库，完成场站设计、订单评价及任务预约；间距模块对分段航迹做解析检测；导出模块输出JSON、CSV和SVG。界面计算在后台线程执行，回放直接使用保存的任务时间，避免“动画位置”和计算结果不一致。图1给出主要流程。')
I('系统流程.png','图1 从地图输入到可复核结果的系统流程')
P('地图一经成功导入便保存为内存快照。磁盘文件被改动不会悄悄改变已计算结果；重新导入或应用编辑后才生成新场景。参数发生修改时，界面提示重新计算，再允许按新结果回放和导出。模型错误和输入错误均保留原场景，避免半完成的编辑污染当前结果。')
H(2,'3.2 场景对象与数据来源')
P('统一场景包含地图宽高、网格步长、建筑、候选起降场、配送点、人群风险区及数据来源说明。坐标原点位于地图左上角，X向右、Y向下，平面坐标和建筑高度单位均为米。建筑以轴对齐矩形近似，允许多个矩形描述复杂建筑；目前未采用精确多边形或倾斜建筑模型。')
T('表1 核心场景字段及其作用',['对象','主要字段','模型用途'],[
['地图设置','宽、高、步长、来源','统一米制尺度和离散范围'],
['建筑','编号、位置、长宽、高度','判断固定高度下的障碍'],
['候选场站','编号、名称、坐标','枚举两个场站的组合'],
['配送点','编号、坐标、需求权重','订单目的地及抽样权重'],
['人群区','中心、椭圆半径、权重','形成相对暴露风险场']], [2.2,5.4,7.05])
P('本次实验输入为项目内自建模拟园区data/demo_scene.json：宽960米、高640米，含10栋建筑、8个候选场站、10个配送点和4个人群热点。建筑名称仅用于示意，不代表已经调查的真实校园。图2为图片导入示例，定量实验统一使用上述JSON场景。校园卫星截图尚缺尺度、楼高和业务点位，未纳入定量结果。')
P('实验输入和结果的完整性以文件校验值记录于附录。数据说明同时保留“模拟、估计或核实”的来源要求：当前数据属于模拟；未来导入实际园区时，应逐项记录图源、获取日期、尺度依据、楼高依据、人工修正记录和需求估计口径。仅更换一张底图，不等于建立了经核实的真实案例。')
H(2,'3.3 图片导入与可编辑组件')
P('图片导入使用Pillow在本地处理。程序依据颜色阈值获得候选掩膜，通过形态学开运算减少文字与细线干扰，再提取连通区域并生成轴对齐矩形候选。提供灰色、暖色、蓝灰及手动取色等模式，用户可以调整颜色容差和最小面积。该方法适合颜色相对规整的平面地图；复杂卫星图、阴影、树冠和旋转建筑可能造成误检或漏检，目前没有经过卫星建筑分割准确率评估。')
P('导入后必须确认整图宽度或通过两点已知距离定标。若已知实长为L、对应像素距离为d，则比例s=L/d；平面位置和尺寸按该比例转换。建筑高度独立于平面比例，缩放地图不修改楼高。用户逐栋或批量填写楼高；未确认尺度、仍有未填写高度时，程序阻止直接仿真并提示待补项目。')
I('组件编辑器.png','图2 地图组件编辑器与手动属性录入界面  模拟园区')
P('建筑、起降场、配送点和人群区均为独立组件，可在程序内添加、删除、复制、拖动和编辑属性；建筑和人群区可拖动控制点调整尺寸。编辑支持撤销、重做、草稿保存和重开，JSON可嵌入底图，避免拷贝项目时丢失图片。道路和绿地目前作为底图参照，不参与独立通行计算；自动建议的业务点位仍需人工确认。')
P('为改善放大时的可读性，底图最长边保留至3072像素并使用高质量重采样；大幅缩放时只裁切和绘制可视区域。Windows端启用原生高DPI感知，文字和控件按系统缩放显示。底图分辨率只影响显示，建筑几何与航路仍由米制组件数据计算。')
H(2,'3.4 建筑约束与人员暴露风险场')
P('对巡航高度H和建筑高度h，若h+Δh≥H，则建筑成为该高度下的障碍，并在平面矩形外扩Δxy。本实验H=45米、Δh=5米、Δxy=8米。已知高度可以允许从较低建筑上方通行，但由于没有爬升下降过程，该结果只能用于给定高度平面的比较。固定关闭区在整次仿真中不可通行。')
E('阻塞条件：h + Δh ≥ H；平面障碍为建筑矩形向外扩展 Δxy。')
P('Primatesta等分别研究了城市环境中的无人机地面风险地图[6]与风险感知航路规划[7]，为在空间规划中显式考虑风险提供了研究依据。本作品以可编辑人员热点构造简化暴露场，用于比较航路；尚未复现文献中的完整地面风险模型，热点权重也未经过实际数据标定。')
P('人员暴露场以基础值和椭圆高斯热点叠加构成，超过1时截断。热点的中心、椭圆半径及权重均可编辑。风险值表示路径经过该位置的相对地面人员暴露强度，不表示事故概率，也没有包含飞行器失效概率、坠落扩散和伤害后果。')
E('r(x,y) = min{1, 0.035 + Σk wk exp[-2((x-xk)²/rxk² + (y-yk)²/ryk²)]}  （1）')
P('路径暴露使用路段长度乘中点风险值的离散积分。由于任务沿去程原路返航，每单路径暴露指数为往返积分除以100；除数只是显示尺度。配送悬停和返场悬停虽然纳入间距检测，尚未计入该暴露指数。因此需要把它理解为“飞行路径暴露”，不能据此判断全部任务的总风险。')
E('Rpath = Σe le r(me)；Eorder = 2Rpath / 100。  （2）')
H(2,'3.5 风险加权A星航路规划')
P('程序以默认16米步长建立八邻域栅格。阻塞节点不可通行，对角移动禁止穿越阻塞拐角；线段连接还以不超过3米的间隔检查通行条件。起点和终点在邻近5×5栅格范围内选择最近可接入节点，并保留实际端点到节点的连接线。窄通道可能被栅格遗漏，连接采样也不构成精确CAD碰撞证明。')
P('每条邻接边的代价由距离和暴露共同决定，其中λ为非负风险权重，本实验λ=2。启发函数使用到目标接入节点的欧氏距离。由于边代价不小于几何距离，该启发函数是下界；在当前图、已选接入节点和约束内，A*搜索得到最小加权代价的离散航路。标准算法依据见文献[1]。')
E('c(u,v) = ||u-v|| [1 + λ r((u+v)/2)]。  （3）')
E('f(n) = g(n) + h(n)；h(n) = ||n-goal||。  （4）')
P('航路库为每个候选场站到各配送点预先计算路径并缓存距离、暴露与累计长度。改变地图、巡航高度或风险权重后重新建立航路库；改变订单种子时可以沿用同一规划条件下的航路。所有场站方案使用同一风险加权规划器，“距离优先方案”指场站评分以总航程为目标，不代表该方案另外使用了λ=0的最短距离航路。')
P('本作品将算法核验和业务结果区分。小型构造场景中，测试使用独立Dijkstra搜索[8]计算同一图的目标代价，与A*输出对照至数值精度；另行检查端点、累计长度和每段通行性。该证据支持实现一致性，不能扩大为连续空间或任意地图上的精度认证。')
H(2,'3.6 两起降场选址与多指标评分')
P('Hong等[9]从航程受限的补能站覆盖问题研究无人机配送设施布局。本作品在给定候选位置中选择两个起降场，比较其时效与暴露表现；当前模型没有补能网络与续航约束，因此选址结果不能直接替代文献所讨论的充电设施规划。')
P('选择两个场站时，程序枚举所有可用候选场站的两两组合。默认8个候选均可用时共28个组合；障碍或关闭区中的候选先被排除。对每个组合使用相同设计订单和基线调度评价时间、路径暴露、总航程、场站等待及失败数。设计随机种子固定20365744，与所有评价种子分离。')
P('各指标在本次候选集合内做min-max归一化。若该指标最大最小值相等，归一值取0；无成功订单导致指标缺失时取1。综合方案权重为暴露0.45、配送时间0.30、总航程0.15、场站等待0.10，每个失败订单附加1000分惩罚。距离方案采用归一化总航程和同样的失败惩罚。权重为当前研究设定，尚未通过实际偏好调查标定。')
E('zq = (q-qmin)/(qmax-qmin)。  （5）')
E('J综合 = 0.45z暴露 + 0.30z时间 + 0.15z航程 + 0.10z场站等待 + 1000N失败。  （6）')
E('J距离 = z航程 + 1000N失败。  （7）')
P('固定布局优先使用S1与S5；若其中有候选不可用，则按可用列表顺序补足。综合和距离方案在候选集合内选择评分最小者，同分按场站编号确定，保证可复现。该枚举能获得给定候选集合、设计订单与评分规则下的最小分组合，不能声称获得连续选址或城市规模选址的全局最优。')
P('为使调度配对实验可比较，站点设计统一关闭错峰，之后冻结站点，在独立评价订单上比较两种调度。本版属于先选址、再调度的顺序优化，尚未把空中预约约束纳入选址联合优化。候选规模增大后组合数量按m(m-1)/2增长，城市规模计算应采用筛选、分解或近似方法。')
H(2,'3.7 订单生成与场站资源预约')
P('订单生成使用可复现伪随机数，根据配送点需求权重抽取目的地，再生成订单创建时刻。正常和关闭场景为30单、到达窗口1200秒；高峰为60单、到达窗口800秒。到达时间为均匀随机数映射并取整，不将其描述为经过数据拟合的泊松过程。默认订单从创建起600秒内完成配送为准时。')
P('5架无人机按顺序归属两个选定场站，通常形成3架与2架的配置。订单按创建时刻、编号依次处理；每个候选无人机需同时满足空闲、场站起飞服务可用、航路可达等条件。程序先计算最早起飞准备时隙，完成25秒准备后出发，以9米/秒飞向目的地，处理20秒后返航，返场占用20秒降落服务。每个场站的起飞和降落共用一份日历。')
P('在可行候选中选择最早送达者，同分按无人机编号确定。日历一经预约不被后续订单调整，属于按订单顺序的贪心预约，并不保证全局最短等待。平均配送时间包含等待无人机、场站排队、错峰、去程和配送处理；订单送达后返航和降落不再计入该单配送时间，但会影响后续任务可用时刻。')
H(2,'3.8 连续时间间距检测与错峰')
P('每次配送任务的空中部分拆分为去程折线、目的地悬停、返程折线和必要的返场悬停。起飞准备和降落服务视为地面阶段，不参与当前空中间距判断。两架无人机在重叠时间区间内的相对位置为r+vτ，求解二次不等式即可得到距离严格小于阈值的时间区间，不依赖逐秒采样。基于预测航迹检查间距属于冲突检测问题，相关建模方法的综述可参见Kuchar和Yang[10]。')
E('||r + vτ||² < dmin²。  （8）')
P('检测输出接近开始与结束时刻、最接近时刻、最小距离及对应订单。对同一任务对跨越航路折点但时间连续的片段进行合并，计为一次事件。冲突累计时长是每个任务对接近时长之和，同一时刻若有多对接近会分别累计。本文使用“间距不足事件”表示上述模型判据，不把它等同于真实碰撞。')
P('启用错峰后，对每架候选无人机，先按场站日历确定基准准备时隙，再检查完整候选任务与已接受空中预约。发现接近时按5秒步长推迟请求时刻，并重新计算场站服务及返场等待；最大额外推迟为600秒。选择最早可送达的可行任务；全部候选都超限时记录airspace_delay_limit失败，无航路时记录unreachable失败。')
P('场站等待定义为原起飞排队与返场排队之和，错峰等待单列为相对基准准备时隙的额外推迟。由于推迟还会影响后续任务可用时间，平均配送时间的增量通常大于单列错峰等待。整个排程完成后，程序再次独立检测所有航迹，包括基线调度，以防仅因调度分支未检查而漏报。')
P('该方法只调整任务出发时刻，不改变已接受预约，也没有在飞行途中进行避碰控制或突发重规划。5秒离散搜索和600秒上限可能拒绝实际存在其他解的订单；模型内零间距不足不代表真实航空安全保证。')
P('在动态环境规划方面，Phillips和Likhachev[11]提出以安全时间区间组织搜索的SIPP；Sharon等[12]提出面向多智能体路径规划的冲突搜索方法。两者为后续时空规划提供了参照。本作品使用既定航路和顺序预约，仅搜索出发时刻，未实现SIPP或CBS，也未获得这些方法所研究的多智能体最优性保证。')
H(2,'3.9 桌面界面与结果导出')
I('仿真地图.png','图3 旧基础入口的单次回放  非当前位置优选')
P('主界面集中提供场景、订单量、巡航高度、风险权重、机队规模及错峰开关。地图显示建筑、风险热区、候选和入选场站、配送点及无人机位置；用户可切换图层、播放暂停、拖动时间与调整倍速。基线发生接近时以标记突出位置；方案对比页展示各布局的多项指标。')
I('方案对比.png','图4 旧基础入口的三方案对比  非当前V0.7结果')
P('完整JSON保存场景、参数、种子、候选评分、航路、订单、任务、服务日历和冲突事件；CSV便于核对指标、任务和失败类型，SVG便于放大查看地图及对比图。批量实验另行输出原始运行表、配对差值表、汇总表和清单。MATLAB脚本可作为后续绘图入口，本机尚未实际运行，不把它列为已验证的软件联动成果。')
H(2,'3.10 实验设计与评价口径')
P('采用3种场景×5个评价种子×3种布局×2种调度的完整方案组合，得到90条运行指标和45组配对比较。每个场景先使用设计种子选址一次，随后在评价种子20261015至20261019上复用布局。种子只是随机流标识，不是实测日期。每一组比较使用相同订单、航路、布局、无人机数量和服务参数，仅改变错峰开关。')
T('表2 仿真主要参数',['参数','设定','说明'],[
['模拟园区','960×640米','10栋建筑，8候选场站，10配送点'],
['巡航与栅格','45米；16米','固定高度，八邻域'],
['建筑间距','平面8米；垂直5米','研究参数'],
['风险权重','λ=2','所有布局共用'],
['机队与速度','5架；9米/秒','场站固定归属'],
['服务时间','起飞25秒；降落20秒；配送20秒','每场站一个服务位'],
['准时阈值','下单后600秒','含等待与配送处理'],
['错峰参数','间距20米；步长5秒；上限600秒','研究设定，非监管标准'],
['订单负荷','正常30单/1200秒；高峰60单/800秒','模拟随机到达'],
['关闭区域','(470,200)，宽75，高150米','整次运行生效，按地图比例缩放']], [3.0,5.0,6.65])
P('关闭场景中，关闭矩形在建图前设置，并在设计和评价全过程生效。每种场景分别重新选址，因此这里比较的是在各自已知条件下设计的方案，不能用来证明同一布局对途中突发关闭的鲁棒性。')
P('平均配送时间和平均暴露以成功订单为分母；完成率与准时率以全部订单为分母，失败订单计为未完成和未准时。报告同时检查失败数，以避免只在成功子集上获得好看的均值。90条指标是方案评价记录，不是90次真实飞行；相同订单流在不同方案中重复评价，合计事件和完成次数不代表独立业务量。')
E('完成率 = N成功/N总；准时率 = N按时送达/N总。  （9）')
E('平均配送时间 = Σ成功订单(t送达-t创建)/N成功。  （10）')
P('汇总表对同一场景、布局和调度的5个评价种子计算均值及样本标准差。误差线为样本标准差，不是置信区间；5个种子只提供初步稳定性证据，不据此声称统计显著或普遍有效。')
H(2,'3.11 实验结果与时效权衡')
P('保存的45组配对结果中，基线间距不足事件合计700次，错峰为0次；两种调度均无失败订单，完成率均为100%。按45组运行的平均配送时间差值等权计算，错峰增加35.53秒，该值不按订单数加权。表4给出历史全部布局的间距事件和配送时间，图5、图6展示综合风险布局的变化。')
rows=[]
for s,sn in SCENARIOS:
    for p,pn in PLANS:
        rows.append([sn+'\n'+pn,f'{val(s,p,"baseline","air_conflict_count"):.2f} ± {sd(s,p,"baseline","air_conflict_count"):.2f} → 0',f'{val(s,p,"baseline","mean_delivery"):.2f} → {val(s,p,"staggered","mean_delivery"):.2f}'])
T('表3 五个评价种子的间距事件与配送时间',['场景与布局','间距不足事件\n基线→错峰 / 次','平均配送时间\n基线→错峰 / 秒'],rows,[3.9,5.0,5.75])
P('表4间距事件给出基线均值±样本标准差；错峰9种组合均为0±0次。配送时间栏为跨种子均值。完整的时间与其他指标标准差见附录所列summary.csv，避免仅凭表中均值判断稳定性。')
I('间距不足事件.png','图5 综合风险布局的间距不足事件  均值与样本标准差')
I('配送时间.png','图6 综合风险布局的平均配送时间  均值与样本标准差')
rows=[]
for s,sn in SCENARIOS:
    for p,pn in PLANS:
        rows.append([sn+'\n'+pn,f'{val(s,p,"baseline","mean_exposure"):.3f} → {val(s,p,"staggered","mean_exposure"):.3f}',f'{val(s,p,"staggered","mean_airspace_delay"):.2f}',f'{100*val(s,p,"baseline","on_time_rate"):.1f} → {100*val(s,p,"staggered","on_time_rate"):.1f}'])
T('表4 人员路径暴露 错峰等待与准时率',['场景与布局','暴露指数\n基线→错峰','错峰等待\n秒/单','准时率\n基线→错峰 / %'],rows,[3.6,4.1,2.9,4.05])
P('表5各值均为5个评价种子的均值。所有组合完成率均为100%、失败数均为0；准时率反映完成时间而非能否最终完成。暴露指数没有纳入悬停，不能把错峰后指数下降解释为全部任务风险降低。')
I('人员暴露.png','图7 综合风险布局的每单路径暴露指数  均值与样本标准差')
H(2,'3.12 结果解释与方案选择')
P('正常场景下，固定、距离优先和综合风险布局分别选中S1+S5、S3+S7和S2+S6。错峰后距离优先的平均配送时间为123.71秒、每单暴露1.093；综合风险为137.15秒、暴露0.849。综合方案的暴露均值相对距离方案降低约22.3%，同时配送时间增加13.44秒，体现当前权重下对人员活动区域的回避代价。该相对差异只针对所设地图和需求。')
P('高峰场景中，距离优先与综合风险均选中S6+S8，因此两者结果相同。错峰后平均配送时间778.18秒，准时率39.0%；固定布局为882.68秒和32.3%。虽然所有订单最终完成，运行仍不满足大部分订单600秒内送达的时效目标。可优先研究增加机队、调整站点归属和服务能力，而不是通过放宽间距来掩盖拥堵。')
P('关闭场景中，综合风险布局错峰后的平均配送时间135.58秒、暴露0.846；距离优先为133.18秒、暴露1.150。两者时效接近，但路径暴露差异明显，说明在本场景下仅按航程选址会遗漏人群分布。由于每个场景重新设计站点，这仍不是对同一站点组合的突发事件应对验证。')
P('错峰可能使无人机选择发生变化，而各机固定归属的场站不同，因而总体航程与暴露也可能变化；不能假设“只推迟时间”就一定使全部路径指标保持不变。另一方面，暴露没有覆盖悬停，现有指标不足以计算等待带来的完整风险和能耗代价。')
H(2,'3.13 软件验证与可复现性')
P('2026年10月17日使用配套Python执行python -m unittest discover -s tests -v，41项测试全部通过，耗时16.919秒。覆盖航路目标代价、建筑约束、资源不重叠、连续时间接近、错峰失败、数据导出、Excel校验、图片处理、组件编辑及草稿状态等。测试用于核查实现是否符合既定模型；模型是否代表现实仍需要外部数据与实地验证。')
T('表5 已执行的关键核验',['核验对象','核验方式','结果与边界'],[
['航路正确性','与独立Dijkstra代价对照；端点与通行性检查','通过；限当前离散图'],
['调度约束','无人机任务和共享服务位时段不重叠','通过；预约式模型'],
['间距检测','亚秒交叉、悬停、相切、时间不重叠、事件合并','通过；分段匀速模型'],
['失败统计','不可达、错峰超限及分母检查','通过；保留失败原因'],
['地图编辑','高度修改、定标、撤销重做、JSON往返','通过；高度保持手动'],
['图片显示','细线保留、大图缩放、自包含底图','通过；不代表识别精度'],
['界面检查','大小窗口、高DPI、编辑与回放操作','历史检查通过；详见验证记录']], [2.8,6.0,5.85])
P('现有桌面检查记录覆盖主界面1380×830与1120×720逻辑窗口、编辑器1280×840与1000×680逻辑窗口，以及本机200%缩放。高DPI显示和底图对齐已有操作检查，未据此声称对所有操作系统与显示设备完成兼容性认证。')
P('复现步骤为：保留完整项目目录，使用含Tkinter的Python 3.10以上环境；图片导入额外安装Pillow。先用内置JSON运行单次结果，再使用独立输出目录运行配对实验，对照90条原始指标、45条差值和汇总表。参数、种子和数据文件路径随manifest保存。各文件和命令见附录A。')
H(2,'3.14 实际地图接入与应用流程')
P('实际使用时先选定边界清晰的小型园区，从具有使用权限的图源获得清晰地图并记录出处。通过已知边长或两点实距建立尺度，核查旋转、透视和拼接影响；用管理资料、测绘资料或明确标注的估计方法填写建筑高度。对长条、倾斜或连体建筑，应使用多个矩形保守近似并人工检查。')
P('随后在编辑器中核实可用起降位置、配送位置和需求权重，删除不符合实际场地条件的候选。人群区应依据调查或可追溯假设设置，不能把图上颜色当作人群密度。确认数据完整后保存JSON，先检查不可达航路和异常任务，再进行多方案、多种子比较。')
P('用于方案讨论时，应同时展示时间、准时率、完成率、路径暴露和间距事件，并能从异常指标回查具体订单。导出结果可供教师或园区管理者讨论站点与容量；现场实施前，还需单独完成场地、机型、气象、能源、通信和运行规则的核实，本系统输出不代替这些工作。')

H(1,'4 特色与创新之处')
H(2,'4.1 可编辑地图与算法输入直接衔接')
P('将导入图片后的建筑候选转成可编辑模型组件，要求人工确认尺度和楼高，使用户可以通过修改实际影响航路的几何与高度来调整模型。编辑结果直接进入同一仿真引擎，减少底图展示与计算地图脱节的问题。创新定位为面向使用过程的工程集成，尚未提出新的建筑识别算法。')
H(2,'4.2 风险选址与连续时间调度串联')
P('在一个原型内贯通风险加权航路、有限候选组合选址、场站服务预约和连续时间间距检测，使用户能够从“选址评分”追溯到“路径与任务”，再解释错峰代价。相较只展示最短航线或飞行动画，系统提供间距事件位置及任务时间证据；现阶段仍是顺序优化，不把模块组合包装为已证明的联合最优算法。')
H(2,'4.3 配对设计与可审计输出')
P('采用独立设计订单冻结场站，再在共享评价订单上切换错峰，减少因重新选址和重新生成订单而混淆比较的风险。错峰等待、场站等待、失败订单及准时率分别记录；原始运行表、配对差值、完整任务JSON和文件校验值共同支撑复核。当前结果明确呈现效率代价和高峰不足，保留对方案不利的信息。')

H(1,'5 总结')
P('本作品已经形成可运行的Python桌面仿真原型，实现地图导入与组件编辑、固定高度障碍建模、风险加权A*、两个场站组合选址、订单分配、共享服务预约、连续时间间距检测和错峰出发。41项测试通过，模拟园区90条运行指标和45组配对结果可以复核。现有证据支持在所设模型中通过错峰消除间距不足，并量化其时效代价。')
P('研究同时暴露出三项主要限制：真实地图数据尚未校准；风险和飞行模型仍较简化；原5种子与新增20种子的两张既有地图仍不足以支持普遍化结论，且截图示例存在全面落后的反例。高峰场景的低准时率说明仅优化时隙不能解决容量不足。')
P('后续优先建立一个有尺度、楼高和来源记录的实际园区案例，再围绕风险权重、机队规模、服务时间、栅格步长及间距阈值进行敏感性实验，增加评价种子并记录运行耗时。其后补入悬停能耗和暴露、风与定位误差，以及动态关闭重规划。真实应用验证应在这些条件逐步补齐后开展。')

H(1,'参考文献')
P('[1] HART P E, NILSSON N J, RAPHAEL B. A Formal Basis for the Heuristic Determination of Minimum Cost Paths[J]. IEEE Transactions on Systems Science and Cybernetics, 1968, 4(2): 100-107. DOI: 10.1109/TSSC.1968.300136.')
P('[2] OTTO A, AGATZ N, CAMPBELL J, et al. Optimization approaches for civil applications of unmanned aerial vehicles (UAVs) or aerial drones: A survey[J]. Networks, 2018, 72(4): 411-458. DOI: 10.1002/net.21818.')
P('[3] MURRAY C C, CHU A G. The flying sidekick traveling salesman problem: Optimization of drone-assisted parcel delivery[J]. Transportation Research Part C: Emerging Technologies, 2015, 54: 86-109. DOI: 10.1016/j.trc.2015.03.005.')
P('[4] DORLING K, HEINRICHS J, MESSIER G G, et al. Vehicle Routing Problems for Drone Delivery[J]. IEEE Transactions on Systems, Man, and Cybernetics: Systems, 2017, 47(1): 70-85. DOI: 10.1109/TSMC.2016.2582745.')
P('[5] KONG J, WEI L, JIANG X. A Literature Review of Vehicle and Drone Delivery Routing Problems in Different Synchronization Level Scenarios[J]. Drones, 2026, 10(3): 206. DOI: 10.3390/drones10030206.')
P('[6] PRIMATESTA S, RIZZO A, LA COUR-HARBO A. Ground Risk Map for Unmanned Aircraft in Urban Environments[J]. Journal of Intelligent & Robotic Systems, 2020, 97(3-4): 489-509. DOI: 10.1007/s10846-019-01015-z.')
P('[7] PRIMATESTA S, GUGLIERI G, RIZZO A. A Risk-Aware Path Planning Strategy for UAVs in Urban Environments[J]. Journal of Intelligent & Robotic Systems, 2019, 95(2): 629-643. DOI: 10.1007/s10846-018-0924-3.')
P('[8] DIJKSTRA E W. A note on two problems in connexion with graphs[J]. Numerische Mathematik, 1959, 1(1): 269-271. DOI: 10.1007/BF01386390.')
P('[9] HONG I, KUBY M, MURRAY A T. A range-restricted recharging station coverage model for drone delivery service planning[J]. Transportation Research Part C: Emerging Technologies, 2018, 90: 198-212. DOI: 10.1016/j.trc.2018.02.017.')
P('[10] KUCHAR J K, YANG L C. A review of conflict detection and resolution modeling methods[J]. IEEE Transactions on Intelligent Transportation Systems, 2000, 1(4): 179-189. DOI: 10.1109/6979.898217.')
P('[11] PHILLIPS M, LIKHACHEV M. SIPP: Safe interval path planning for dynamic environments[C]//2011 IEEE International Conference on Robotics and Automation. 2011: 5628-5635. DOI: 10.1109/ICRA.2011.5980306.')
P('[12] SHARON G, STERN R, FELNER A, et al. Conflict-based search for optimal multi-agent pathfinding[J]. Artificial Intelligence, 2015, 219: 40-66. DOI: 10.1016/j.artint.2014.11.006.')

H(1,'附录A 代码与复现索引')
P('以下路径均以配套Python项目根目录为起点。报告引用的运行数据来自results/safety，截图来自docs/images；新增地图编辑能力的核验见tests及docs/验证记录.md。报告制作未重写保存的实验数据。')
T('表A1 程序与证据文件',['相对路径','内容'],[
['run.py','桌面、单次、批量与配对实验入口'],
['engine.py','场景、风险、A*、场站评分、任务调度'],
['airspace.py','分段航迹及连续时间间距审计'],
['image_map.py','本地建筑候选提取与底图处理'],
['map_document.py','组件事务、校验、定标、撤销重做'],
['map_editor.py','可视化地图编辑和手动楼高'],
['map_import.py','Excel/JSON导入与字段定位'],
['app.py、ui.py、display.py','界面、回放、高DPI与地图绘制'],
['reporting.py、study.py','导出、配对差值及统计报告'],
['tests/','41项自动核验'],
['data/demo_scene.json','本报告模拟场景输入'],
['results/safety/','原始、汇总、配对表与30份运行JSON'],
['docs/验证记录.md','桌面与高DPI历史检查记录'],
['matlab/analyze_results.m','可选分析脚本，尚未实际运行验证']], [6.6,8.05])
P('在项目目录运行下列命令。为保留本报告证据，重新运行实验时分别使用results/sites_reproduction与results/safety_reproduction，按对应流程比较原始指标。测试不修改实验结果。')
C('python run.py\npython -m unittest discover -s tests -v\npython run.py --mode safety `\n  --scene data/demo_scene.json `\n  --output results/report_reproduction')
P('单次导出包含result.json、comparison.csv、jobs.csv、failed.csv、conflicts.csv、map.svg和comparison.svg。配对实验保存90条运行指标、45条配对记录和30份JSON，每份JSON中包含3种布局。summary.csv每个指标均有有效运行数、均值和样本标准差。')
T('表A2 报告所用文件的SHA256校验值',['文件','SHA256'],[[str(p.relative_to(ROOT)).replace('\\','/').replace('/','/\n'),sha(p)[:32]+'\n'+sha(p)[32:]] for p in [ROOT/'data/demo_scene.json',ROOT/'results/safety/manifest.json',ROOT/'results/safety/raw_metrics.csv',ROOT/'results/safety/paired_comparison.csv',ROOT/'results/safety/summary.csv']],[5.8,8.4])
P('注：路径在“/”后换行，SHA256值按32位分行；校验时按顺序拼接，不包含换行。')

H(1,'附录B 人工智能辅助使用说明')
P('本项目使用OpenAI Codex/ChatGPT开展生成式人工智能辅助工作，涉及选题与模型讨论、Python程序和测试脚本编写及修改、界面和地图编辑功能迭代、本轮多代理协作评审与修改、说明文字整理、报告初稿、表格排版及图表制作。报告的模型说明、结果分析和总结段落为AI辅助整理内容，应由参赛团队结合代码与原始结果审核后采用。')
P('实验表格和统计图读取已保存的CSV生成，界面图片为程序运行截图，未使用生成式图片冒充地图、实验现象或真实飞行记录。演示视频使用Windows系统离线合成语音，画面来自实际Tk程序和既有录屏。数据均为模拟或含假设的输入；没有生成参赛人员、单位、联系方式、手写签名、实际测绘数据、专利或论文成果。')
P('AI辅助不能替代参赛者对原创性、数据真实性、软件许可和结论的责任。参赛团队应依据官网《参赛指南》（https://www.siac.net.cn/article/2）及《竞赛诚信规范手册》（https://www.siac.net.cn/article/26）核对允许的使用范围，如实补充个人实际工作、审核与修改记录，并在正式提交前完成模型理解、数据核查和承诺书手写签署。')


# Revision 2026-10-18: the active V0.7 evidence and historical safety study have separate scopes.
SITE = list(csv.DictReader((ROOT/'results/sites_v1/summary.csv').open(encoding='utf-8-sig')))
site_idx={(r['scenario'],r['plan']):r for r in SITE}
def sv(sc,pl,k):return float(site_idx[sc,pl][k])
def replace_p(prefix, text):
    for i,item in enumerate(content):
        if item[0]=='p' and item[1].startswith(prefix):
            content[i]=('p',text);return
    raise ValueError(prefix)
replace_p('在960米×640米模拟园区中','当前V0.7在960米×640米模拟园区内，以3个设计种子的正常与高峰样本等权评价28种位置组合，固定5架无人机及每站一个服务位，再冻结同一位置与3+2架配比，以5个独立种子开展30条方案评价。运行优选选择S6+S8：正常平均配送143.35秒、路径暴露0.797；距离优先为123.71秒、1.093。高峰运行优选为778.18秒、准时率39.00%，距离优先为731.00秒、39.67%，未实现各指标均优。另保留旧选址流程的90条调度评价与45组配对证据，间距事件合计700次降为0次、运行等权平均时间增加35.53秒；两套结果不混用。')
replace_p('本作品提出三个可用仿真检验的问题','本作品检验两个层级的问题：当前V0.7在正常与高峰共同设计下，固定位置、距离优先、运行优选形成怎样的时效与暴露权衡；历史安全配对实验在相同订单、位置和航路下，错峰如何改变间距事件与等待。当前位置评价冻结正常与高峰的同一布局；历史关闭场景则按场景重新选址，两者证据范围不同。')
replace_p('本次实验输入为项目内自建模拟园区','当前V0.7与历史安全实验均以项目自建960×640米模拟园区为基础，含10栋建筑、8个候选位置、10个配送点、4个人群热点。当前选址使用results/sites_v1/scene.json，历史配对使用data/demo_scene.json及results/safety/manifest.json记录的场景；来源、处理后的场景和校验值分开保存。建筑名称、楼高、人群和需求均为模拟设定，不能视为真实调查。清华大学官网导览图仅用于真实图源接入与识别草稿，尺度、楼高、需求尚待核实，未纳入定量效果。')
replace_p('图片导入使用Pillow','图片与编辑显示使用可选Pillow。清华官网导览图的图例分类与轮廓处理另使用NumPy、OpenCV，Windows离线OCR可产生名称候选。通用模式依颜色和连通区域产生建筑候选，适合颜色相对规整的平面地图；复杂卫星图、阴影、树冠和倾斜建筑可能误检或漏检。当前没有建立识别准确率数据集。核心仿真和Excel/JSON导入使用Python标准库，不依赖这些图像包。')
replace_p('建筑、起降场、配送点和人群区均为独立组件','建筑、起降场、配送点和人群区均为独立组件，可在程序内增删、复制、拖动和编辑；道路轮廓可编辑并概括显示，但不作为无人机通行障碍。编辑支持撤销、重做、草稿保存和重开，JSON可嵌入底图。主仿真图使用与规划一致的建筑矩形简图，只把当前高度下构成障碍的建筑显示为障碍；原图保留供人工核对。自动建议点位仍需人工确认。')
a=next(i for i,x in enumerate(content) if x[0]=='h' and x[2].startswith('3.6 '))
b=next(i for i,x in enumerate(content) if x[0]=='h' and x[2].startswith('3.7 '))
current=[
('h',2,'3.6 当前V0.7起飞位置设计'),
('p','系统在可用候选位置中枚举组合。1架无人机使用1个起飞点，2—20架使用2个起飞点；各布局总机队相同，按候选点顺序均衡分配，奇数时前站多一架。当前证据为5架与8候选点，共28种布局。所有站点采用相同起降服务参数，设施等级、建设成本及预算不参与当前流程。'),
('p','设计种子为20365744、20470473、20575202。每个组合使用各设计种子的正常与高峰订单并开启相同错峰约束，正常与高峰等权。固定位置优先S1、S5，不可用时按可用顺序补足；距离优先先比较正常设计样本失败数，再比较总航程。运行优选依次最小化平均失败率、平均非准时率、平均每单超时秒数、平均配送秒数加30倍路径暴露，同分按站点编号确定。30为人为权衡系数，尚未通过业务偏好校准。'),
('equation','J运行 = lexmin (失败率, 1-准时率, 每单超时秒数, 配送秒数 + 30×路径暴露)。'),
('p','词典序比较先保证前项不劣，再考察后项。有限枚举只保证在给定候选、3个设计种子及设定目标下取最小值，不保证独立评价、连续选址或真实运营的全局最优。选址阶段纳入预约式错峰，但运行调度仍按订单顺序贪心预约，没有滚动重优化。'),
('p','当前位置方案为固定S1+S5、距离S3+S7、运行优选S6+S8，各为前站3架、后站2架。正常与高峰独立评价冻结同一位置和配比，设计种子与5个评价种子分离。无人机数量变化后必须重新选址。'),
('p','历史safety实验使用engine.evaluate_plans的旧流程：每个场景单设计种子20365744，先用基线调度选址，综合风险采用暴露、时间、航程、场站等待的min-max归一化加权（0.45、0.30、0.15、0.10）及失败惩罚。它与当前site_selection.py的跨场景词典序设计不同，仅作为历史调度对照，不能用其正常S2+S6或137.15秒替代当前S6+S8和143.35秒。')]
content[a:b]=current
# Insert the current evidence before the retained historical experiment section.
a=next(i for i,x in enumerate(content) if x[0]=='h' and x[2].startswith('3.10 '))
rows=[]
for sc,sn in [('normal','正常'),('peak','高峰')]:
    for pl in ['fixed','distance','combined']:
        r=site_idx[sc,pl]
        rows.append([sn+'\n'+r['plan_name'],r['configuration'].replace(' + ','\n'),f"{float(r['mean_delivery']):.2f} ± {float(r['mean_delivery_std']):.2f}",f"{float(r['mean_exposure']):.3f} ± {float(r['mean_exposure_std']):.3f}",f"{float(r['on_time_rate'])*100:.2f}%"])
v07=[('h',2,'3.10 当前V0.7独立评价'),
('p','结果来自results/sites_v1。评价种子20261015—20261019与3个设计种子互不重复，同一种子同一场景的三个方案共享订单。2场景×5种子×3方案共30条评价记录；每种场景与方案报告5次运行等权均值和样本标准差，不能视为置信区间或真实飞行样本。P95为每次运行成功订单最近秩P95的跨运行均值。'),
('table','表3 当前V0.7正常与高峰评价',['场景与方案','位置及机队','配送秒数\n均值±标准差','路径暴露\n均值±标准差','准时率'],rows,[2.3,3.1,3.5,3.5,2.2]),
('p','全部30条当前评价记录均完成所有订单，失败数和间距不足事件为0；这只支持当前理想模型和给定样本。正常运行优选相对距离优先的暴露降低27.1%，配送时间增加19.64秒。高峰暴露降低26.6%，但配送时间增加47.18秒、准时率低0.67个百分点。独立评价没有复制设计阶段对早期目标的排序优势，不能声称运行优选在高峰时效上优于距离优先。'),
('p','高峰运行优选平均778.18秒、准时率39.00%，即多数订单超过600秒。该不利结果完整保留，表明当前位置与5架机的服务能力不足。模型未证明所选位置在需求扰动、真实人群数据或不同机队下稳定占优；5个评价种子只构成有限初步证据。'),
('h',2,'3.11 历史安全配对实验设计')]
content[a:a+1]=v07
for i,item in enumerate(content):
    if item[0]=='h':
        swaps={'3.11 实验结果与时效权衡':'3.12 历史安全配对结果','3.12 结果解释与方案选择':'3.13 历史结果的适用范围','3.13 软件验证与可复现性':'3.14 软件验证与可复现性','3.14 实际地图接入与应用流程':'3.15 实际地图接入与应用流程'}
        if item[2] in swaps:content[i]=('h',item[1],swaps[item[2]])
    elif item[0]=='table' and item[1].startswith('表3 五个'):
        content[i]=('table',item[1].replace('表3','表4 历史'),*item[2:])
    elif item[0]=='table' and item[1].startswith('表4 人员'):
        content[i]=('table',item[1].replace('表4','表5 历史'),*item[2:])
    elif item[0]=='table' and item[1].startswith('表5 已执行'):
        content[i]=('table',item[1].replace('表5','表6'),*item[2:])
replace_p('2026年10月17日使用配套Python','2026年10月17日的41项测试为历史记录。本轮2026年10月18日使用配套Python重新运行完整测试，80项全部通过，耗时30.538秒（首轮77项，新增3项独立审计边界检查）；原始日志为.verification/competition_20261018/full_tests_round2.txt，交付验证摘要见docs/参赛验收/技术验证.md。本轮另实际启动Tk工作台检查，不能从历史项数推断当前通过。测试覆盖实现与设定模型的一致性，不能替代真实数据、识别准确率或真实飞行验证。')
replace_p('复现步骤为','复现使用含Tkinter的Python 3.10以上环境。核心仿真与Excel/JSON无需第三方包；图片功能按requirements-image.txt安装Pillow、NumPy、OpenCV，研究绘图依requirements-analysis.txt安装Matplotlib。当前V0.7先运行--mode sites并选择独立输出目录，核对30条原始记录、冻结配置和3设计/5评价种子；历史--mode safety另行复现，不能比较错套的布局。')
replace_p('在一个原型内贯通风险加权航路','在一个原型内贯通风险加权航路、有限候选位置组合、场站预约和连续时间间距检测。当前V0.7把正常/高峰需求与错峰约束带入位置设计，采用分离设计/评价种子并冻结同一位置与机队进行跨场景评价。调度仍为按订单贪心预约，未证明位置、航路和调度的联合全局最优。')
replace_p('本作品已经形成可运行的Python','本作品形成Python V0.7桌面研究原型，支持可编辑地图、固定高度航路、1—20架机配置、同一布局的正常/高峰独立评价、预约错峰、连续时间间距审计、回放与导出。当前30条评价揭示运行优选的暴露优势及高峰时效不足；另保留旧选址下90条评价与45组调度配对，两类结果均可追溯到原始文件。')
replace_p('以下路径均以配套Python项目根目录为起点','以下路径以项目根目录为起点。当前V0.7主证据为results/sites_v1；历史安全配对为results/safety。真实校园图源与处理记录见data/真实校园地图/清华大学的使用与来源说明.md及来源记录.json，识别草稿尚未核实尺度、楼高和需求。本报告没有将真实底图接入误写为实测效果。')
for i,item in enumerate(content):
    if item[0]=='table' and item[1].startswith('表A1'):
        rows2=[list(r) for r in item[3]]
        rows2=[['tests/','本轮完整测试以当前验证日志为准'] if r[0]=='tests/' else r for r in rows2]
        rows2 += [['site_selection.py、site_ui.py','当前V0.7位置优选和交互工作台'],['results/sites_v1/','当前30条评价、28候选、配置、种子、完整任务JSON']]
        content[i]=('table',item[1],item[2],rows2,item[4])
    if item[0]=='code' and 'report_reproduction' in item[1]:
        content[i]=('code','python run.py\npython -m unittest discover -s tests -v\npython run.py --mode sites --drones 5 --output results/sites_reproduction\npython run.py --mode safety --output results/safety_reproduction')
content.insert(next(i for i,x in enumerate(content) if x[0]=='h' and x[2].startswith('附录B')),('p','当前结果校验：results/sites_v1/manifest.json记录场景、配置、3个设计种子、5个评价种子及导出源码校验；study.json包含候选设计和完整评价。重跑耗时与生成日期允许变化，确定性指标应逐项对比。历史文件的哈希不能用作当前源码版本的证明。'))


a=next(i for i,x in enumerate(content) if x[0]=='h' and x[2]=='3.11 历史安全配对实验设计')
content[a:a]=[
('h',2,'3.10A 冻结布局追加种子检验'),
('p','为检验结论是否依赖原5个评价种子，本轮冻结既有布局和参数，不重新设计或调参，对默认模拟园区与既有真实截图示例两张地图，各使用20261020—20261039共20个新增订单种子，分别运行正常和高峰。2地图×2场景×20种子×3方案共240条新增方案运行、10800条重复评价任务记录。这是同两张既有地图的新订单样本，不能称为新增实测园区或真实订单。'),
('table','表3A 新增20种子高峰差值及逐指标优平劣',['地图与基线','指标','运行优选减基线\n均值 ± 样本SD','优/平/劣'],[
['默认园区\n距离优先','准时率百分点','-4.17 ± 3.65','0 / 2 / 18'],
['默认园区\n距离优先','配送秒数','+88.63 ± 54.43','1 / 0 / 19'],
['默认园区\n距离优先','路径暴露','-0.335 ± 0.109','20 / 0 / 0'],
['截图示例\n固定位置','准时率百分点','-1.83 ± 4.92','7 / 0 / 13'],
['截图示例\n固定位置','配送秒数','+42.34 ± 39.84','3 / 0 / 17'],
['截图示例\n固定位置','路径暴露','+0.064 ± 0.018','0 / 0 / 20']], [3.2,3.0,5.1,3.3]),
('p','原5种子截图示例高峰运行优选650.52秒、准时率46.00%，固定位置586.11秒、52.33%，来源为results/user_map_300m/测试报告.md。追加20种子中，默认高峰相对固定位置，运行优选准时率平均增加3.00个百分点、16优1平3劣；相对距离优先却平均降低4.17个百分点，配送更慢88.63秒。截图示例高峰相对固定位置，运行优选配送更慢42.34秒，路径暴露20次均劣。新增样本进一步显示方案依赖地图与目标，不能用单一总胜率或“普遍优于距离方案”概括。这里没有进行统计显著性检验，样本标准差也不是置信区间。'),
('p','截图示例采用既有30米巡航高度和5架机，底图来自实际地图截图，但尺度、楼高、需求及人群包含假设；其空间边界不同于清华官网未定标草稿，不能混称真实校园验证。源研究、场景、源码与结果哈希见results/competition_v07/manifest.json。原始差值、范围和7项指标的逐项优平劣均保存；复现命令为python cases/run_competition_holdout.py --output results/competition_v07_reproduction。'),
('p','独立轨迹核查从导出的路线点和任务时刻重建分段运动，不调用生产间距检测器，并检查机队任务及服务日历。空中/地面切换同一瞬间的零时长交接在现有模型中不计持续间距事件，已有33个同站交接记录，不能解释为真实起降安全；详见技术验证文档。')]


for i,item in enumerate(content):
    if item[0]=='table':
        title=item[1]
        for old,new in [('表3 当前','表2 当前'),('表3A 新增','表3 新增'),('表2 仿真','表4 仿真'),('表4 历史','表5 历史'),('表5 历史','表6 历史'),('表6 已执行','表7 已执行')]:
            if title.startswith(old):
                content[i]=('table',title.replace(old,new,1),*item[2:]);break
    elif item[0]=='p':
        text2=item[1].replace('表4给出历史全部','表5给出历史全部').replace('表4间距事件','表5间距事件').replace('表5各值均为5个','表6各值均为5个')
        content[i]=('p',text2)

# Second V0.7 review adds read-only decision explanations, preserving old evidence.
from diagnosis_materials import apply_round2
content, DESCRIPTION, INNOVATION, VALUE = apply_round2(content, ROOT)
shutil.copy2(ROOT/'docs/images/site-diagnosis.png', FIG/'决策诊断.png')
shutil.copy2(ROOT/'docs/images/site-diagnosis-adverse.png', FIG/'反例诊断.png')

# Retain the exact screenshots used in the report under its portable figure folder.
for source,target in [('component-editor.png','组件编辑器.png'),('simulation-map.png','仿真地图.png'),('plan-comparison.png','方案对比.png')]:
    shutil.copy2(ROOT/'docs/images'/source, FIG/target)

# Figure PDFs are rendered by the bundled Poppler outside this authoring script.
# The docx is assembled on the second invocation, once figure PNGs exist.
if '--figures-only' in sys.argv:
    print('Figure PDFs and template contract ready:',FIG)
    sys.exit(0)

doc=Document(REF)
for required in ['Body Text','Heading 2','Heading 3']:
    if required not in doc.styles:
        style=doc.styles.add_style(required,WD_STYLE_TYPE.PARAGRAPH)
        style.base_style=doc.styles['Normal' if required=='Body Text' else 'Heading 1']
        if required.startswith('Heading'):
            outline=OxmlElement('w:outlineLvl');outline.set(qn('w:val'),str(int(required[-1])-1))
            style._element.get_or_add_pPr().append(outline)
paras=doc.paragraphs
for p in paras[18:]: p._element.getparent().remove(p._element)

def font(run,size=12,bold=False,name='仿宋'):
    run.font.name=name; run.font.size=Pt(size); run.font.bold=bold; run.font.color.rgb=RGBColor(0,0,0)
    rf=run._element.get_or_add_rPr().get_or_add_rFonts()
    for k in ['eastAsia','ascii','hAnsi']:rf.set(qn('w:'+k),name)
    return run
def base(p,indent=True):
    f=p.paragraph_format
    f.left_indent=Cm(0); f.right_indent=Cm(0); f.first_line_indent=Pt(24 if indent else 0)
    f.line_spacing=1.25; f.space_before=Pt(0); f.space_after=Pt(5)
    f.widow_control=True; f.keep_with_next=False
    pp=p._p.get_or_add_pPr()
    snap=pp.find(qn('w:snapToGrid'))
    if snap is None:snap=OxmlElement('w:snapToGrid');pp.append(snap)
    snap.set(qn('w:val'),'0')
    ind=pp.find(qn('w:ind'))
    if ind is not None:
        for key in ['firstLineChars','hangingChars','leftChars','rightChars']:
            ind.attrib.pop(qn('w:'+key),None)
    p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
    return p
def ptext(t='',indent=True,align=None):
    p=base(doc.add_paragraph(),indent); font(p.add_run(t))
    if align is not None:p.alignment=align
    return p
def heading(t,level=1,pagebreak=False):
    p=doc.add_paragraph(style='Heading '+str(min(level,3)))
    pPr=p._p.get_or_add_pPr()
    for n in pPr.findall(qn('w:numPr')): pPr.remove(n)
    base(p,False); p.paragraph_format.keep_with_next=True
    p.paragraph_format.space_before=Pt(9);p.paragraph_format.space_after=Pt(6)
    p.paragraph_format.page_break_before=pagebreak
    font(p.add_run(t),12,True,'仿宋')
    return p
def page():
    # Apply the break to the next real paragraph; no empty paragraph can spill.
    return
def table(headers,rows,widths,blank=False):
    widths=[w*min(1,14.6/sum(widths)) for w in widths]
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    for col,w in zip(t.columns,widths):col.width=Cm(w)
    for cell,w,h in zip(t.rows[0].cells,widths,headers):cell.width=Cm(w);cell.text=h
    for row in rows:
        cells=t.add_row().cells
        for cell,w,value in zip(cells,widths,row):cell.width=Cm(w);cell.text=str(value)
    props=t._tbl.tblPr
    if headers==['文件','SHA256']:
        table_width=props.find(qn('w:tblW'))
        table_width.set(qn('w:type'),'dxa');table_width.set(qn('w:w'),str(round(sum(widths)*1440/2.54)))
    borders=OxmlElement('w:tblBorders')
    for edge in ['top','left','bottom','right','insideH','insideV']:
        e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
    props.append(borders)
    for i,row in enumerate(t.rows):
        trPr=row._tr.get_or_add_trPr();trPr.append(OxmlElement('w:cantSplit'))
        if i==0:
            r=OxmlElement('w:tblHeader');trPr.append(r)
        for cell in row.cells:
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcPr=cell._tc.get_or_add_tcPr();mar=OxmlElement('w:tcMar')
            for edge in ['top','bottom','left','right']:
                el=OxmlElement('w:'+edge);el.set(qn('w:w'),'45');el.set(qn('w:type'),'dxa');mar.append(el)
            tcPr.append(mar)
            if i==0:
                sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'F0F2F5');tcPr.append(sh)
            for p in cell.paragraphs:
                base(p,False);p.paragraph_format.line_spacing=1.05;p.paragraph_format.space_after=Pt(1)
                p.paragraph_format.space_before=Pt(1);p.alignment=WD_ALIGN_PARAGRAPH.LEFT
                if headers==['文件','SHA256']:
                    p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.keep_together=True
                if False:
                    p.paragraph_format.keep_with_next=True
                for r in p.runs:font(r,12,i==0)
    # Space after table via a following modest paragraph, never an empty page.
    p=doc.add_paragraph();p.paragraph_format.space_after=Pt(3)
    p.paragraph_format.line_spacing=Pt(1);font(p.add_run(),1)
    return t

# Cover: preserve source paragraphs, logo and overall formal layout.
cover=doc.paragraphs
for i,p in enumerate(cover):
    snap=OxmlElement('w:snapToGrid');snap.set(qn('w:val'),'0');p._p.get_or_add_pPr().append(snap)
    if i in [2,3,4,16]:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
cover[2].style=doc.styles['Title']
for i,txt,size in [(2,'中国仿真创新应用大赛',20),(3,'数字建模与智能决策赛道',20),(4,'智能决策方向作品设计方案',16)]:
    cover[i].clear();font(cover[i].add_run(txt),size,True,'宋体')
    cover[i].paragraph_format.first_line_indent=Pt(0);cover[i].paragraph_format.space_after=Pt(12)
for i in [0,1,5,6,7,8,13,14,15,17]:
    cover[i].clear();cover[i].paragraph_format.space_before=Pt(0);cover[i].paragraph_format.space_after=Pt(0);cover[i].paragraph_format.line_spacing=1
    font(cover[i].add_run(),14)
for i,txt in [(9,'项目名称：\n'+TITLE),(10,'申请人（主持人）：________________'),(11,'所在单位：新疆大学'),(12,'联系电话：________________________')]:
    cover[i].clear();base(cover[i],False);cover[i].paragraph_format.left_indent=Cm(.6)
    cover[i].paragraph_format.line_spacing=1.8;cover[i].paragraph_format.space_after=Pt(12)
    font(cover[i].add_run(txt))
cover[5].paragraph_format.space_after=Pt(35)
cover[15].paragraph_format.space_after=Pt(30)
cover[16].paragraph_format.first_line_indent=Pt(0)
outline=OxmlElement('w:outlineLvl');outline.set(qn('w:val'),'9');cover[2]._p.get_or_add_pPr().append(outline)

# Standard body styles (official requirement overrides template's empty Normal style).
for name in ['Normal','Body Text']:
    st=doc.styles[name];st.font.name='仿宋';st.font.size=Pt(12);st.font.color.rgb=RGBColor(0,0,0)
    st._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'仿宋')
    snap=OxmlElement('w:snapToGrid');snap.set(qn('w:val'),'0');st._element.get_or_add_pPr().append(snap)
for name in ['Title','Heading 1','Heading 2','Heading 3']:
    st=doc.styles[name];st.font.color.rgb=RGBColor(0,0,0)
    st._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'宋体')

page();heading('中国仿真创新应用大赛作品信息表',pagebreak=True)
t=table(['作品名称',TITLE,'',''],[['所在学校','新疆大学','邮政编码',''],['联系人','','手机',''],['电话','','Email',''],['通讯地址','','','']],[2.4,4.925,2.4,4.925])
t.rows[0].cells[1].merge(t.rows[0].cells[3])
t.rows[-1].cells[1].merge(t.rows[-1].cells[3])
heading('参赛者',2)
table(['序号','姓名','性别','联系方式','微信','所学专业'],[[i,'','','','',''] for i in range(1,6)],[1.4,2.0,1.4,3.25,2.8,3.8])
heading('指导教师',2)
table(['序号','姓名','性别','联系方式','专业','职称'],[[i,'','','','',''] for i in range(1,3)],[1.4,2.0,1.4,3.25,3.3,3.3])
ptext('说明：参赛者顺序应与报名系统一致，获奖证书人员排序以报名系统填写顺序为准。',False)
page();heading('作品信息表 续',pagebreak=True)
for label,t in [('作品内容简介 限300字以内',DESCRIPTION),('创新点 限200字以内',INNOVATION),('推广应用价值 限200字以内',VALUE)]:
    heading(label,2);ptext(t)
ptext('项目成果：是否发表论文  是□ / 否□\n是否已申请专利  是□ / 否□\n其他：________________________',False)
ptext('是否为迭代作品：是□ / 否☑',False)
ptext('情况说明：________________________________________',False)
ptext('若为迭代作品，请说明迭代部分并提供更新30%以上的证明；不超过500字，可添加图片。',False)
page();heading('中国仿真创新应用大赛诚信承诺书',pagebreak=True)
commit=(OFFICIAL/'中国仿真创新应用大赛诚信承诺书.txt').read_text(encoding='utf-8-sig').splitlines()
commit=[re.sub(r'参赛成员：\s+，','参赛成员：________________，',line) for line in commit]
for line in commit[1:]:
    if not line.strip():continue
    if line.lstrip().startswith('团队成员'):
        ptext('团队成员（签字）：\n\n________________________________________________\n________________________________________________',False)
    elif '年' in line and '月' in line and '日' in line and len(line.strip())<30:
        ptext('年        月        日',False,WD_ALIGN_PARAGRAPH.RIGHT)
    else:ptext(line.strip())

page();heading('目录',pagebreak=True)
page_index={}
page_info=QA/'word-pages.json'
if page_info.exists():
    page_records=json.loads(page_info.read_text(encoding='utf-8-sig'))
    # This intermediate package still has three form pages; split_report removes them.
    form_offset=0 if any('中国仿真创新应用大赛作品信息表' in r['text'] for r in page_records) else 3
    for record in page_records:
        for line in record['text'].splitlines():
            if '\t' not in line:page_index[line.strip()]=record['page']+form_offset
for part in content:
    if part[0]=='h' and part[1]==1:
        title=part[2]
        p=ptext(title+'\t'+str(page_index.get(title,'')),False)
        p.paragraph_format.space_after=Pt(13)
        p.paragraph_format.tab_stops.add_tab_stop(Cm(14.0),WD_TAB_ALIGNMENT.RIGHT,WD_TAB_LEADER.DOTS)
ptext('正文依次说明模型、实现、配对实验和应用边界；附录给出代码索引、复现命令和人工智能辅助说明。',False)

# Front-matter headings are visible labels, not entries in the body TOC.
front=doc.styles.add_style('Front Matter Heading',WD_STYLE_TYPE.PARAGRAPH)
front.base_style=doc.styles['Normal']
for existing in doc.paragraphs:
    if existing.style.name.startswith('Heading'):
        existing.style=front

for item in content:
    typ=item[0]
    if typ=='h':
        _,level,t=item
        # Top-level chapters begin on a fresh page; appendix body is independent.
        heading(t,level,level==1 and (t in ['摘要','参考文献'] or t.startswith('附录')))
    elif typ=='p':
        p=ptext(item[1],not item[1].startswith('['))
        if item[1].startswith('['):
            p.alignment=WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.keep_together=True
        if item[1].startswith('AI辅助不能替代'):p.alignment=WD_ALIGN_PARAGRAPH.LEFT
        if item[1].startswith('采用独立设计订单冻结场站'):
            p.paragraph_format.keep_together=True
    elif typ=='equation':
        p=ptext(item[1],False,WD_ALIGN_PARAGRAPH.LEFT);p.paragraph_format.space_before=Pt(3);p.paragraph_format.space_after=Pt(9)
    elif typ=='code':
        lines=item[1].splitlines()
        for i,line in enumerate(lines):
            p=ptext(line,False,WD_ALIGN_PARAGRAPH.LEFT);p.paragraph_format.line_spacing=1.1
            p.paragraph_format.keep_with_next=(i<len(lines)-1)
    elif typ=='table':
        _,cap,headers,rows,widths=item
        p=ptext(cap,False,WD_ALIGN_PARAGRAPH.CENTER);p.paragraph_format.keep_with_next=True
        table(headers,rows,widths)
    elif typ=='image':
        _,name,caption=item
        p=doc.add_paragraph();base(p,False);p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next=True
        p.add_run().add_picture(str(FIG/name),width=Cm(14.6))
        p=ptext(caption,False,WD_ALIGN_PARAGRAPH.CENTER);p.paragraph_format.space_after=Pt(10)

# Add page numbers, leave original header/logo untouched.
footer=doc.sections[0].footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
footer.paragraph_format.first_line_indent=Pt(0)
r=font(footer.add_run(),12)
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');r._r.addnext(fld)
settings=doc.settings.element
update=OxmlElement('w:updateFields');update.set(qn('w:val'),'true');settings.append(update)
doc.core_properties.title=TITLE
doc.core_properties.subject='中国仿真创新应用大赛作品设计方案'
doc.core_properties.author='';doc.core_properties.last_modified_by=''
doc.core_properties.comments=''
doc.save(DOCX)

# python-docx serialization need not rewrite opaque source parts: restore them exactly.
mutable={'word/document.xml','word/styles.xml','word/settings.xml','word/_rels/document.xml.rels','[Content_Types].xml','docProps/core.xml'}
with ZipFile(DOCX) as z:parts={i.filename:z.read(i.filename) for i in z.infolist() if not i.is_dir()}
for name,data in source_parts.items():
    if name not in mutable:parts[name]=data
tmp=DOCX.with_suffix('.tmp.docx')
with ZipFile(tmp,'w',ZIP_DEFLATED) as z:
    for name,data in parts.items():z.writestr(name,data)
tmp.replace(DOCX)
assert sha(REF)==re.search(r'SHA-256：(\w+)',artifact).group(1)
for name,data in source_parts.items():
    if name not in mutable:assert parts[name]==data,name

# The editable Markdown contains the same report narrative, tables and references.
md=[f'# {TITLE}\n','中国仿真创新应用大赛｜数字建模与智能决策赛道｜智能决策方向\n',
    '申请人（主持人）：\n\n所在单位：新疆大学\n\n联系电话：\n',
    '## 作品信息表\n','作品名称：'+TITLE+'\n\n所在学校：新疆大学\n\n邮政编码：\n\n联系人：\n\n通讯地址：\n\n电话：\n\n手机：\n\nEmail：\n',
    '|序号|姓名|性别|联系方式|微信|所学专业|\n|---|---|---|---|---|---|\n'+''.join(f'|{i}||||||\n' for i in range(1,6)),
    '|指导教师序号|姓名|性别|联系方式|专业|职称|\n|---|---|---|---|---|---|\n|1||||||\n|2||||||\n',
    '### 作品内容简介\n\n'+DESCRIPTION+'\n','### 创新点\n\n'+INNOVATION+'\n','### 推广应用价值\n\n'+VALUE+'\n',
    '### 项目成果\n\n论文：是□ / 否□\n\n专利：是□ / 否□\n\n其他：\n\n是否为迭代作品：是□ / 否☑\n\n情况说明：\n',
    '## 诚信承诺书\n\n'+'\n\n'.join(commit[1:])+'\n']
for item in content:
    if item[0]=='h':md.append('#'*(item[1]+1)+' '+item[2]+'\n')
    elif item[0] in ['p','equation']:md.append(item[1]+'\n')
    elif item[0]=='code':md.append('```powershell\n'+item[1]+'\n```\n')
    elif item[0]=='image':md.append(f'![{item[2]}](图表/{item[1]})\n\n{item[2]}\n')
    elif item[0]=='table':
        _,cap,headers,rows,_=item
        md.append(cap+'\n\n'+'|'+'|'.join(h.replace('\n','<br>') for h in headers)+'|\n'+'|'+'|'.join([':---:' if headers==['文件','SHA256'] else '---']*len(headers))+'|\n'+''.join('|'+'|'.join(str(c).replace('\n','<br>') for c in row)+'|\n' for row in rows))
MD.write_text('\n'.join(md),encoding='utf-8')

evidence={'report_title':TITLE,'reference_sha256':sha(REF),'input_files':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'data/demo_scene.json',ROOT/'results/safety/raw_metrics.csv',ROOT/'results/safety/summary.csv']},'tests':{'status':'see current verification logs','historical_count':41,'historical_date':'2026-10-17'},'raw_rows':len(RAW),'paired_rows':len(list(csv.DictReader((ROOT/'results/safety/paired_comparison.csv').open(encoding='utf-8-sig')))),'baseline_conflicts':sum(float(r['air_conflict_count']) for r in RAW if r['dispatch']=='baseline'),'staggered_conflicts':sum(float(r['air_conflict_count']) for r in RAW if r['dispatch']=='staggered'),'information_form_character_counts':{'description':len(DESCRIPTION),'innovation':len(INNOVATION),'value':len(VALUE)},'font':'仿宋 12pt','render':'Microsoft Word 16 COM + bundled Poppler'}
(QA/'report-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print('Created',DOCX,'\n',MD)
print('Chinese characters in narrative:',sum(len(x[1]) for x in content if x[0]=='p'))

# Export standalone administrative copies while retaining the combined main report.
from lxml import etree
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(DOCX) as z: allparts={n:z.read(n) for n in z.namelist()}
tree=etree.fromstring(allparts['word/document.xml'])
body=tree.find('w:body',NS);children=list(body)
labels=[''.join(n.xpath('.//w:t/text()',namespaces=NS)) for n in children]
first=labels.index('中国仿真创新应用大赛作品信息表');second=labels.index('中国仿真创新应用大赛诚信承诺书');end=labels.index('目录')
forms=ROOT/'参赛材料/独立表单';forms.mkdir(exist_ok=True)
for name,nodes in [('作品信息表',children[first:second]),('诚信承诺书',children[second:end])]:
    outtree=deepcopy(tree);outbody=outtree.find('w:body',NS)
    for n in list(outbody):outbody.remove(n)
    for n in nodes:outbody.append(deepcopy(n))
    outbody.append(deepcopy(body.find('w:sectPr',NS)))
    for br in outbody[0].xpath('./w:pPr/w:pageBreakBefore',namespaces=NS):br.getparent().remove(br)
    parts2=dict(allparts);parts2['word/document.xml']=etree.tostring(outtree,xml_declaration=True,encoding='UTF-8',standalone=True)
    with ZipFile(forms/(name+'.docx'),'w',ZIP_DEFLATED) as z:
        for n,data in parts2.items():z.writestr(n,data)
mdtext=MD.read_text(encoding='utf-8');a=mdtext.index('## 作品信息表');b=mdtext.index('## 诚信承诺书');c=mdtext.index('## 摘要')
(forms/'作品信息表.md').write_text(mdtext[a:b].rstrip()+'\n',encoding='utf-8');(forms/'诚信承诺书.md').write_text(mdtext[b:c].rstrip()+'\n',encoding='utf-8')
