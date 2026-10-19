import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { Presentation, PresentationFile } from '@oai/artifact-tool';
const SOURCE=path.dirname(fileURLToPath(import.meta.url));
let ROOT=SOURCE;while(!await fs.stat(path.join(ROOT,'engine.py')).catch(()=>false)) ROOT=path.dirname(ROOT);
const BUILD=path.join(ROOT,'.verification','materials_rebuild');await fs.mkdir(BUILD,{recursive:true});
const SKILL=process.env.PRESENTATION_SKILL_DIR; if(!SKILL) throw new Error('Set PRESENTATION_SKILL_DIR to the installed presentations skill directory');
const PYTHON=process.env.RUNTIME_PYTHON; if(!PYTHON) throw new Error('Set RUNTIME_PYTHON to the authoring Python executable');
const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const study=JSON.parse(await fs.readFile(path.join(ROOT,'results/sites_v1/study.json'),'utf8'));
const summaries=study.summary;
const round2=Object.fromEntries(await Promise.all(['demo_5','user_map_h30_d5'].map(async key=>[key,JSON.parse(await fs.readFile(path.join(ROOT,'results/decision_v07_round2',key,'decision_diagnostics.json'),'utf8'))])));
for(const value of Object.values(round2)){if(JSON.stringify(value.evaluation_seeds)!==JSON.stringify(Array.from({length:20},(_,i)=>20261040+i)))throw new Error('Unexpected round-2 evaluation seeds');}
function diagnosticPlan(key,scenario){const sc=round2[key].scenarios.find(s=>s.scenario===scenario);return {sc,plan:sc.plans.find(p=>p.plan==='combined')};}
function signed(value,digits=2){return (value>=0?'+':'')+value.toFixed(digits);}
const OUT=path.join(ROOT,'参赛材料/答辩PPT');await fs.mkdir(OUT,{recursive:true});await fs.mkdir(path.join(BUILD,'deck-renders'),{recursive:true});
const p=Presentation.create({slideSize:{width:1600,height:900}});
const C={navy:'#102A56',ink:'#253C52',gray:'#566B7D',teal:'#087F78',line:'#D9E1E8',white:'#FFFFFF'};
function txt(s,value,x,y,w,h,size=30,color=C.ink,bold=false){let a=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});a.text=value;a.text.style={fontSize:size,typeface:'Microsoft YaHei',color,bold,alignment:'left',verticalAlignment:'top',autoFit:'none',wrap:'square',insets:0};return a;}
function base(title,sub,source){let s=p.slides.add();s.background.fill=C.white;txt(s,title,80,62,1440,72,48,C.navy,true);if(sub)txt(s,sub,83,146,1430,64,27,C.gray);txt(s,source,82,835,1330,40,19,C.gray);txt(s,String(p.slides.items.length).padStart(2,'0'),1450,831,80,44,25,C.navy,true);return s;}
function para(s,title,body,y){txt(s,title,85,y,1430,52,34,C.teal,true);txt(s,body,85,y+65,1420,125,30,C.ink);}
function notes(s,text,sources=[]){s.speakerNotes.text=text+'\n\n来源：\n'+sources.join('\n');}
function table(s,values,x,y,w,h,widths){const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});t.borders.assign({fill:C.line,width:.8,style:'solid'});for(let r=0;r<values.length;r++){t.rows[r].height=h/values.length;for(let c=0;c<values[0].length;c++){const z=t.getCell(r,c);z.fill=r===0?C.navy:(r%2?'#F5F8FA':C.white);z.text.style={fontSize:29,typeface:'Microsoft YaHei',color:r===0?C.white:C.ink,bold:r===0,alignment:c===0?'left':'center',verticalAlignment:'middle',insets:15,autoFit:'none'};}}return t;}
async function screenshot(s,filename,x,y,w,h){const b=await fs.readFile(path.join(ROOT,filename));s.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:'image/png',alt:filename,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
let s=base('园区低空配送风险仿真与起降位置决策','新疆大学   数字建模与智能决策赛道   智能决策方向','Python V0.7第二轮诊断增强   研究仿真候选版');
txt(s,'面向园区末端配送的低空风险仿真与起降场选址系统',84,246,810,160,50,C.navy,true);
txt(s,'比较位置、时效与路径暴露\n显示取舍与不宜采用的场景',86,469,790,150,34,C.ink);
txt(s,'离线桌面原型\n模拟数据   尚无真实飞行验证',86,690,790,99,29,C.gray);
await screenshot(s,'docs/images/simulation-map.png',935,250,570,510);
txt(s,'历史基础入口回放示意',940,765,570,37,21,C.gray);
notes(s,'建议20秒。说明作品定位与单位。研究固定巡航高度下的园区前期方案比较，没有真实飞行安全或运营认证。成员姓名和指导教师尚待本人填入。',['README.md','results/sites_v1/manifest.json']);
s=base('园区方案比较与人工决策','输入地图并核实假设，查看三候选，依据目标和取舍判断采用或暂缓','本轮增加只读解释，原航路、位置设计与调度算法保持一致');
para(s,'三候选与基线差', '固定位置、距离优先、设计优选。逐场景显示相对两基线的准时率、配送时间与暴露差。',245);
para(s,'目标检查与取舍', '默认90%是团队可调准时率研究目标。四指标帕累托关系说明被支配或非劣，非劣仍可能有取舍。',446);
para(s,'用户决定采用或暂缓', '三候选均未达到目标时提示当前场景不推荐采用。存在达标候选时也不自动推荐，由用户结合偏好判断。',647);
notes(s,'建议25秒。90%只检查场景跨运行等权平均准时率，不是官方线、法规或逐单保证。四轴为失败率降低、准时率提高、配送秒数降低和路径暴露降低；仅针对本次三方案。',['decision_support.py','docs/参赛验收/第二轮实验协议.json']);
s=base('V0.7第二轮决策诊断工作台','地图输入与1—20架机配置，目标和取舍检查，回放与证据导出','实际程序界面：docs/images/site-diagnosis.png；未选定默认推荐方案');
await screenshot(s,'docs/images/site-diagnosis.png',80,224,1440,574);
notes(s,'建议35秒。现场先看团队可调目标，再看正常取舍及高峰全不达标。回放需主动选行，导出全研究无需选行；修改目标须应用后再回放或导出。设计优选即原运行优选，旧raw保留combined和旧名，名称只表示设计选择。图片尺度和楼高需人工确认。',['site_ui.py','decision_support.py','docs/起飞点优选.md']);
s=base('固定高度航路与连续时间间距','沿建筑高度约束规划，用分段轨迹审计模型中的接近事件','标准A*与相对运动方法为已有方法；本作品贡献是约束衔接、交互和可审计输出');
para(s,'风险加权A*', '16米八邻域；建筑高度＋5米达到巡航高度时绕行，平面外扩8米。代价为距离×（1＋λ×中点暴露）。',243);
para(s,'路径人员暴露', '模拟高斯人群热点形成相对暴露场，往返路径积分除以100。尚未包含悬停暴露，不能解释为事故概率。',446);
para(s,'连续时间与错峰', '只查共同空中的正时长区间，地面与瞬时交接不计。20米阈值、5秒步长推迟，默认等待上限600秒。',647);
notes(s,'建议30秒。间距、缓冲和权重是研究参数。连续时间检测包含去程、配送悬停、返程和返场等待悬停。固定高度匀速折线模型没有真实动力学、导航误差或避碰控制。',['engine.py','airspace.py','tests/test_airspace.py']);
s=base('正常与高峰共同设计起飞位置','3个设计种子选择位置，再用5个互不重叠种子冻结评价','当前入口site_selection.py；不采用历史min-max综合评分，也不考虑设施等级和成本');
para(s,'公平比较28种布局', '5架机、8候选点，选择2点；各布局总机队相同、按顺序3＋2分配。设计中正常和高峰等权、均开启错峰。',245);
para(s,'三种候选', '固定位置S1＋S5；距离优先S3＋S7；设计优选S6＋S8。设计优选原名运行优选，旧raw文件保留原名。',446);
para(s,'原排序与稳定性边界', '全样本第2层已区分候选，30未决胜。两图各2/3留一改变位置，发现浮点近似平局，设计稳定性不足。',647);
notes(s,'建议35秒。原四层为失败率、非准时率、每单超时、配送秒数+30×暴露。原3种子全样本精确复现；逐次留一每图3次中2次改变。默认去掉20470473后第二层仅-5.55e-17，精确选S4+S7，但跳过1e-8近似平局后第3层实质差+0.9884秒反而更差。分别报告精确/实质首分歧，不修改原排序，也不据留一重选旧布局。',['results/sites_v1/manifest.json','results/decision_v07_round2/design_stability.json','results/decision_v07_round2/demo_5/decision_diagnostics.json','facility.py:_objective']);
function resultRows(sc){return [['方案及位置','配送时间 / 秒','路径暴露','准时率'],...summaries.filter(r=>r.scenario===sc).map(r=>[r.plan_name.replace('运行优选','设计优选')+'\n'+r.configuration,Number(r.mean_delivery).toFixed(2)+' ± '+Number(r.mean_delivery_std).toFixed(2),Number(r.mean_exposure).toFixed(3)+' ± '+Number(r.mean_exposure_std).toFixed(3),(100*Number(r.on_time_rate)).toFixed(2)+'%'])];}
s=base('正常场景的时效与暴露权衡','同一30单负荷、5个独立评价种子、同一冻结位置与机队','来源results/sites_v1/summary.csv；均值±样本标准差，非置信区间');
table(s,resultRows('normal'),82,246,1438,350,[460,390,330,258]);
txt(s,'设计优选相对距离优先存在取舍',86,644,1400,58,36,C.teal,true);
txt(s,'路径暴露降低27.1%，平均配送增加19.64秒。全部方案完成率100%，间距事件0。',86,716,1420,86,31,C.ink);
notes(s,'建议30秒。正常运行优选143.35秒、0.797，距离123.71秒、1.093。暴露下降并非免费时效提升。跨种子样本标准差仅反映这5个种子。',['results/sites_v1/raw_metrics.csv','results/sites_v1/summary.csv']);
s=base('高峰三候选均未达到研究目标','60单在800秒内到达，单笔订单创建后600秒内送达视为准时','来源results/sites_v1/summary.csv；默认90%是团队可调平均准时率研究目标');
table(s,resultRows('peak'),82,246,1438,350,[460,390,330,258]);
txt(s,'当前场景不推荐采用任何方案',86,644,1400,58,36,C.teal,true);
txt(s,'设计优选慢47.18秒、暴露低26.6%，仍需人工判断。等待无人机655.17秒，优先检验周转与容量。',86,716,1420,86,31,C.ink);
notes(s,'建议35秒。39%、778.18秒不满足团队90%研究目标。等待无人机含前序各阶段传导，额外错峰仅12.42秒；这是诊断线索，不能据此证明唯一瓶颈或扩容有效。返场排队影响后续单，不能重复加到本单送达。',['results/sites_v1/raw_metrics.csv','decision_support.py']);
s=base('截图高峰显示被支配与目标未达','截图为原5种子20261015—19的诊断，输入尺度、楼高及需求含假设','图为原5种子；下方为协议后新20种子，旧20261020—39反例保留在报告');
const freshNormal=diagnosticPlan('demo_5','normal').plan.baseline_differences.distance;
const freshPeak=diagnosticPlan('user_map_h30_d5','peak').plan.baseline_differences.fixed;
await screenshot(s,'docs/images/site-diagnosis-adverse.png',80,220,1440,497);
txt(s,`协议后新20种子20261040—59，截图高峰对固定位置：配送差${signed(freshPeak.mean_delivery)}秒，\n暴露差${signed(freshPeak.mean_exposure,3)}，准时率差${signed(freshPeak.on_time_rate*100)}个百分点。`,86,733,1430,86,27,C.ink);
notes(s,'建议25秒。截图原5种子，设计优选对固定位置慢64.41秒，三候选均未达90%目标，设计优选被两基线支配。下方是协议冻结后新20261040—59的20种子，模型位置均不改，2地图240条评价不混算。此前20261020—39截图高峰慢42.34秒仍保留。帕累托仅对本次3候选4指标；90%只检查场景平均。',['docs/images/site-diagnosis-adverse.png','docs/参赛验收/第二轮实验协议.json','results/decision_v07_round2/manifest.json','results/competition_v07/追加种子检验.md']);
s=base('历史安全配对证据单独保留','旧选址流程的3场景×5种子×3布局×2调度，共90条评价、45组配对','来源results/safety/；旧流程每个场景重新选址，不能替代当前V0.7位置评价');
txt(s,'700 次降为 0 次',84,272,1415,130,84,C.navy,true);
txt(s,'保存样本中间距不足事件合计',86,411,1410,58,34,C.gray);
txt(s,'平均配送时间增加 35.53 秒',84,516,1435,88,53,C.teal,true);
txt(s,'按45组运行等权；两种调度均无失败。说明时隙约束的代价，不代表真实飞行安全认证。',86,650,1410,135,31,C.ink);
notes(s,'建议25秒。旧engine.evaluate_plans：单设计种子、关闭错峰选址、min-max综合评分。这里证明同订单、同旧位置与航路切换错峰的模型结果，不能把700次作为当前30条位置评价的基线。',['results/safety/paired_comparison.csv','results/safety/summary.csv','study.py']);
s=base('可复现交付与数据边界','核心与Excel使用标准库，桌面运行需Python3.10及Tkinter','第二轮完整94项测试通过，35.930秒；原80项为前轮记录');
txt(s,'复现入口',85,242,1430,52,34,C.teal,true);
txt(s,'python run.py --mode sites --drones 5 --output results/my_sites\npython tools/diagnose_study.py --study results/my_sites/study.json --output results/my_diagnosis',85,307,1430,72,22,C.ink);
txt(s,'先导出研究，再生成诊断JSON/CSV/Markdown；诊断输出须为新空目录。',85,392,1430,43,23,C.gray);
para(s,'模拟与真实图源分开', '标准园区所有尺度、楼高、需求与人群为模拟。清华官网导览图用于识别与操作草稿，尚待核实尺度、楼高和需求。',449);
para(s,'方法与版权可追溯', '参考文献说明A*等已有方法；报告披露Codex/ChatGPT辅助代码、测试、文字及材料制作，团队须理解并核对全部结果。',650);
notes(s,'建议25秒。命令分两步：run.py导出原研究，tools/diagnose_study.py读取study.json另产出诊断JSON/CSV/Markdown，其输出目录须新建或为空；GUI也可导出全研究与诊断。第二轮94项实际通过35.930秒，日志.verification/competition_20261018/full_tests_decision_round2.txt；80项为前轮。独立诊断和轨迹审计另保存。核心不依赖MATLAB。公开图源不等于已取得传播授权，提交前仍需核实。',['README.md','tools/diagnose_study.py','data/真实校园地图/清华大学/使用与来源说明.md','docs/参赛验收/第二轮证据/']);
s=base('人工决策与下一步验证','正常取舍与高峰拒绝均可导出复核，方案名称不替代用户判断','可解释诊断为工程集成；A*、帕累托及相对运动均为已有方法');
para(s,'可核查的贡献', '输入与三候选比较相连，显示目标、基线差与取舍，解释设计排序和评价反转，并保留不利结果。',245);
para(s,'尚未覆盖', '实测楼高、人群与需求校准，真实动力学、气象、能源、导航误差、滚动重规划及真实飞行验证。',446);
para(s,'优先验证方向', '用户可以暂缓所有未达标候选。下一步用控制实验检验周转与容量干预，再补充经核实的数据与实地验证。',647);
notes(s,'建议25秒。总建议演示300秒。国奖竞争力需通过研究和使用证据提升，不能承诺奖项。回答提问时以输入、模型范围与保存结果为依据。',['results/sites_v1/实验分析.md','docs/起飞点优选.md']);
const budgets=[15,15,40,25,35,30,35,30,20,20,20];
for(let i=0;i<p.slides.items.length;i++){const s=p.slides.items[i];s.speakerNotes.text=s.speakerNotes.text.replace(/建议\d+秒。/,`建议${budgets[i]}秒。`).replace('总建议演示300秒','总预算285秒，另留15秒切换余量');const blob=await p.export({slide:s,format:'png',scale:1.25});await fs.writeFile(path.join(BUILD,'deck-renders',`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));console.log('rendered',i+1);}
const candidate=path.join(BUILD,'candidate-v07.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
await fs.mkdir(path.join(BUILD,'final'),{recursive:true});
const revision=Date.now();const finalPath=path.join(BUILD,'final',`defense-${revision}.pptx`);
const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:candidate,finalPath,pythonExecutable:PYTHON,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','15240000,8572500','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','6','--require-native-table-slide','7'],explicitTotalSlideCount:11,requiredNativeTableOwnerSlides:[6,7],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:['Microsoft YaHei']},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,`deck-validation-${revision}.json`)});
console.log(JSON.stringify({finalPath:result.finalPath,bytes:result.byteCount,sha256:result.finalSha256}));
await fs.copyFile(result.finalPath,path.join(OUT,'园区低空配送_答辩PPT_V0.7候选版.pptx'));
process.exit(0);
