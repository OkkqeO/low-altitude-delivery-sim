"""Incremental material copy for the second V0.7 decision-diagnostics review.

Read frozen study diagnostics only. Never changes simulation data or a model.
"""
import json
import re


def apply_round2(content, root):
    base = root / 'results/decision_v07_round2'
    diagnostics = {
        key: json.loads((base/key/'decision_diagnostics.json').read_text(encoding='utf-8'))
        for key in ('demo_5', 'user_map_h30_d5')
    }
    stability=json.loads((base/'design_stability.json').read_text(encoding='utf-8'))
    # The technical export is a list of the full sample and three leave-one-out subsets.
    if isinstance(stability,dict):stability=stability.get('rows',stability.get('comparisons',stability))
    assert isinstance(stability,list) and len(stability)==8
    for diagnostic in diagnostics.values():
        assert diagnostic['evaluation_seeds'] == list(range(20261040, 20261060))
        assert diagnostic['minimum_on_time_rate'] == .90

    def renamed(value):
        if isinstance(value, str):
            return value.replace('运行优选', '设计优选')
        if isinstance(value, tuple):return tuple(renamed(v) for v in value)
        if isinstance(value, list):return [renamed(v) for v in value]
        return value

    content = [renamed(x) for x in content]

    def replace_paragraph(prefix, value):
        for i, item in enumerate(content):
            if item[0] == 'p' and item[1].startswith(prefix):
                content[i] = ('p', value)
                return
        raise ValueError('Missing report paragraph '+prefix)

    replace_paragraph('园区无人机配送的规划需要',
        '园区无人机配送需要在候选位置、送达时效与人员路径暴露之间作出选择。本作品提供离线Python桌面研究原型，将可编辑地图、风险加权航路、两场站组合设计与预约错峰连接为可追溯流程。V0.7第二轮增加只读决策诊断：逐场景展示基线差、四指标帕累托关系、可调准时率研究目标和设计目标首分歧级，取消默认方案推荐，由用户依据证据判断采用、取舍或暂缓。')
    replace_paragraph('当前V0.7在960米×640米模拟园区内',
        '当前位置设计仍按3个设计种子的正常与高峰样本等权比较28种布局，冻结5架机及3+2分配。旧5种子评价中，设计优选正常配送143.35秒、暴露0.797，距离优先123.71秒、1.093，形成时效与暴露取舍；高峰设计优选778.18秒、准时率39.00%，三方案均达不到本轮默认90%准时率研究目标。第二轮在协议冻结后追加20261040—20261059新种子，以两张既有地图240条评价检查诊断，不改变模型和位置，也不混算原5种子与此前20种子。历史700次降至0次和增加35.53秒仅属于旧调度配对。')
    replace_paragraph('系统的直接价值是降低地图试配',
        '系统服务于园区前期方案讨论：用户导入并核实地图后，比较三种候选的时效、路径暴露及服务目标。正常样本中的取舍可以帮助用户表达偏好；高峰三方案均未达目标时，系统明确提示当前场景不推荐采用任何方案。诊断不把“优选”名称当作结论，也不把未达标解释成已找到容量扩充办法；下一步干预仍需控制实验。')
    replace_paragraph('系统将交互与核心计算分离',
        '系统将交互、核心计算和只读诊断分离。地图编辑器形成统一场景；核心引擎建立航路、设计位置并预约任务；间距模块独立审计分段航迹；第二轮decision_support.py读取冻结评价，计算相对固定位置及距离优先的差值、四指标帕累托关系、准时率目标状态与设计目标首分歧级。用户依据这些信息选择候选或暂缓，导出诊断及原始任务证据。诊断不修改A*、位置设计、目标函数或调度。图1为核心计算流程，3.10B说明其后的诊断。')
    replace_paragraph('在一个原型内贯通风险加权航路',
        '本作品的工程贡献是让经人工确认的地图直接进入位置与运行比较，并在输出端说明选择边界。第二轮新增只读诊断，展示设计词典序在哪一层区分候选、独立评价是否反转，以及三方案间是被支配还是需要取舍。取消默认推荐后，用户可因高峰未达研究目标而拒绝全部方案。A*、帕累托和相对运动方法均为已有方法，未提出新优化算法或联合全局最优证明。')
    replace_paragraph('本作品形成Python V0.7桌面研究原型',
        '本作品形成V0.7第二轮诊断增强原型，支持输入与编辑、三候选比较、目标与取舍检查、人工决策、回放及证据导出。正常场景说明较低路径暴露伴随配送时间代价；高峰场景说明三方案均可能需要暂缓采用。报告保留原5种子、此前20种子的反例与历史安全配对，第二轮另用20个未用种子验证诊断输出，不用旧评价反复调参。')
    replace_paragraph('研究同时暴露出三项主要限制',
        '研究仍存在真实数据未校准、风险及飞行模型简化、有限既有地图与种子不足以支持普遍结论等限制。截图示例保留设计优选被支配的反例，两图留一设计也显示选择敏感性。高峰低准时率提示需进一步检验需求与资源条件，当前结果不能证明只调位置或时隙即可达到研究目标；等待分解不能定位唯一瓶颈。')
    replace_paragraph('高峰设计优选平均778.18秒',
        '原5种子高峰设计优选平均778.18秒、准时率39.00%，多数订单超过600秒。本批结果不满足本轮默认90%平均准时率研究目标，提示进一步检验需求与资源条件；没有控制干预实验，不能据此归因于唯一容量瓶颈，或保证调整位置、时隙及机队必然达标。5个评价种子仅构成有限初步证据。')
    replace_paragraph('2026年10月17日的41项测试为历史记录',
        '2026年10月17日41项和10月18日80项测试均为前轮记录。第二轮新增14项诊断校验后，完整94项测试实际通过，耗时35.930秒，原日志为.verification/competition_20261018/full_tests_decision_round2.txt，交付副本见docs/参赛验收/第二轮证据/。冻结原指标对照、独立诊断审计及Tk检查详见本轮技术验证记录与results/decision_v07_round2/manifest.json。测试只支持实现与设定模型一致，不替代真实数据、识别准确率或飞行验证。')
    replace_paragraph('用于方案讨论时，应同时展示',
        '用于方案讨论时，先核实输入和研究准时率目标，再查看正常与高峰的三候选、相对两基线的差值及取舍。目标未达时可暂缓全部候选，不能因名称而默认接受设计优选；存在非劣候选时仍由用户判断时效与暴露偏好。回放用于核对具体订单，导出用于复核同一评价证据。应用前仍需核实场地、机型、气象、能源、通信及运行规则。')

    # Make space for the new Table 4 without breaking existing cross-references.
    for i, item in enumerate(content):
        if item[0] in ('p', 'table'):
            text = re.sub(r'表([4-7])(?!\d)', lambda m:'表'+str(int(m[1])+1), item[1])
            content[i] = (item[0], text, *item[2:])

    def plan(key, scenario):
        sc = next(s for s in diagnostics[key]['scenarios'] if s['scenario']==scenario)
        return sc, next(p for p in sc['plans'] if p['plan']=='combined')

    rows = []
    for key, label in [('demo_5', '默认模拟园区'), ('user_map_h30_d5', '截图假设示例')]:
        for scenario, name in [('normal','正常'), ('peak','高峰')]:
            sc, p = plan(key, scenario)
            relation = {'dominated':'被支配', 'non_dominated':'四指标非劣', 'pending':'待验证'}[p['pareto_status']]
            target = {'below':'未达到', 'meets':'达到', 'pending':'待验证'}[p['service_status']]
            rows.append([label+'\n'+name, f"{100*p['metrics']['on_time_rate']:.2f}%", target, relation])
    normal, normal_plan = plan('demo_5', 'normal')
    peak, peak_plan = plan('user_map_h30_d5', 'peak')
    nd = normal_plan['baseline_differences']['distance']
    pd = peak_plan['baseline_differences']['fixed']
    def sign(v, digits=2):return f'{v:+.{digits}f}'
    layers=[]
    for key,label in [('demo_5','默认园区'),('user_map_h30_d5','截图示例')]:
        for comparison in diagnostics[key]['design_comparisons']:
            baseline={'fixed':'固定位置','distance':'距离优先'}[comparison['baseline']]
            layers.append(f"{label}对{baseline}精确首分歧为第{comparison['first_difference_layer']}层、首实质分歧为第{comparison.get('first_substantive_difference_layer',comparison['first_difference_layer'])}层")
    stability_text=[]
    for key,label in [('demo_5','默认园区'),('user_map_h30_d5','截图示例')]:
        subsets=[r for r in stability if r['case']==key and r['omitted_design_seed'] is not None]
        assert len(subsets)==3
        stability_text.append(f"{label}3次留一中有{sum(bool(r['selection_changed']) for r in subsets)}次改变所选位置")
    addition = [
        ('h',2,'3.10B 第二轮决策诊断与新种子检查'),
        ('p','第二轮仅增强结果解释。“设计优选（原运行优选）”表示原设计样本词典序选择的候选，历史raw文件仍保留plan=combined及旧名称；名称不保证独立评价占优。输入、三候选、取舍或拒绝、人工决策、证据导出构成当前使用流程。算法、位置、机队、原目标与调度均未因新诊断而改变。'),
        ('p','服务准时率默认90%，是团队设置、用户可调的研究目标，不是赛事通过线、法规或运营承诺。按每场景跨运行等权平均准时率判断，不保证每个种子或每笔订单达标。三方案均未达该目标时，提示当前场景不推荐采用任何方案；有达标方案时也只列候选，不自动推荐。每笔订单准时仍指创建后600秒内送达，两种阈值含义不同。'),
        ('p','帕累托比较只考虑本次三候选的失败率降低、准时率提高、平均配送秒数降低和路径暴露降低四个方向。失败率先逐运行计算失败数/订单数，再跨运行等权；配送和暴露按成功订单统计。用1e-8容差判断各轴不劣且至少一轴更优为支配；任一观测缺失则对应指标待验证，四指标关系整体待验证。非劣不意味着全部28种布局或真实世界最优。'),
        ('p','设计目标解释沿用原精确浮点词典序，依次为失败率、非准时率、每单超时秒数、配送秒数+30×暴露；显示与两基线的首分歧层，并对容差内差异提示近似平局。'+ '；'.join(layers)+'。本次第二层若已决定排序，第四层系数30并未参与最后区分；不能把该次选择归因为低暴露偏好。设计/评价反转只是样本差异描述，尚无因果证明。'),
        ('p','协议docs/参赛验收/第二轮实验协议.json在新评价前冻结。两张既有地图均保留5架机和已有位置、分配、模型参数，只追加20261040—20261059共20个未用订单种子。2地图×2场景×20种子×3候选形成240条新方案评价；新旧种子不混算，不根据结果重新设计或调参。完整研究、诊断JSON/CSV/Markdown、原始差值、独立审计与哈希保存在results/decision_v07_round2/。'),
        ('table','表4 第二轮新种子中的设计优选诊断',['地图与场景','平均准时率','90%研究目标','四指标关系'],rows,[4.0,3.0,3.0,4.6]),
        ('p',f"正常例：默认园区相对距离优先，设计优选平均配送差{sign(nd['mean_delivery'])}秒、路径暴露差{sign(nd['mean_exposure'],3)}、准时率差{sign(nd['on_time_rate']*100)}个百分点。该例用于说明用户可见的指标取舍，不把非劣关系自动转换成推荐。"),
        ('p',f"反例：截图假设示例高峰相对固定位置，设计优选配送差{sign(pd['mean_delivery'])}秒、路径暴露差{sign(pd['mean_exposure'],3)}、准时率差{sign(pd['on_time_rate']*100)}个百分点。系统逐轴保存这些差值，并依据完整四指标报告关系；{peak['message']} 不能据此宣称已识别超时的唯一原因或证明增加机队一定有效。"),
        ('p','旧样本高峰设计优选等待无人机655.17秒、额外错峰12.42秒/成功单，可提示优先检验任务周转及资源等待，而不是直接放宽间距。等待无人机包含前序任务各阶段传导；返场排队影响后续任务，不能重复加进本单送达分解。当前诊断没有执行扩容或服务能力干预，因此“容量问题”仍是待控制实验检验的解释。'),
        ('p','另对原设计样本做留一稳定性检查：两地图共43种布局×3设计种子×2场景形成258条布局运行，保留全部3种子及3次留一子集的172条候选得分。'+ '；'.join(stability_text)+'。完整结果见design_stability.json、design_subset_candidate_scores.csv及design_seed_stats.csv。该检查属于样本内选择敏感性，不是新增外部验证；没有用留一结果替换旧布局，也不能据此证明稳定泛化。'),
        ('p','留一还暴露原精确浮点排序的边界：默认园区去掉设计种子20470473时，S4+S7与原S6+S8第二层仅差-5.55×10⁻¹⁷，精确排序选择S4+S7；跳过1e-8内近似平局后，首实质差在第3层每单超时，S4+S7反而增加0.9884秒。因此两种首分歧分别保留，极小差不解释成实质收益。第二轮没有据此修订原排序或替换旧布局；实际采用前仍需另定稳健设计方案并使用新的评价数据。'),
    ]
    index=next(i for i,x in enumerate(content) if x[0]=='h' and x[2]=='3.11 历史安全配对实验设计')
    content[index:index]=addition
    for i,item in enumerate(content):
        if item[0]=='image' and item[1]=='仿真地图.png':
            content[i]=('image','决策诊断.png','图3 默认园区原5种子诊断  达标候选与指标取舍')
        elif item[0]=='image' and item[1]=='方案对比.png':
            content[i]=('image','反例诊断.png','图4 截图示例原5种子诊断  被支配与目标未达')
        elif item[0]=='table' and item[1].startswith('表A1'):
            rows2=[*item[3],['decision_support.py','只读目标、基线差、帕累托与设计首分歧诊断'],['results/decision_v07_round2/','第二轮协议后新种子、诊断与独立审计']]
            content[i]=('table',item[1],item[2],rows2,item[4])
    replace_paragraph('主界面集中提供场景',
        '第二轮工作台不默认选中候选，回放需主动选行，导出全研究及三方案诊断无需选行。修改研究目标仅更新诊断，须应用目标后再回放或导出。图3为默认园区原5评价种子的正常例，设计优选与距离优先在时间和暴露上存在取舍；图4为含假设截图示例的同一批5种子高峰，设计优选被两基线支配，三候选均未达90%研究目标。图4对固定位置配送增加64.41秒，不与此前20种子的42.34秒混用。两图使用原5种子，3.10B才使用本轮新增20种子。')
    description=('面向校园与园区末端配送，提供离线Python桌面研究原型。支持图片、Excel、JSON地图输入和组件编辑，以风险加权A*、候选位置枚举、预约错峰与连续时间间距检查比较固定位置、距离优先、设计优选三候选，支持1—20架机。V0.7第二轮增加只读诊断，展示基线差、四指标取舍、可调准时率研究目标及原设计首分歧级，取消默认推荐，由用户判断采用或暂缓。冻结布局后独立评价并保留反例、回放和完整导出；尚无真实飞行验证。')
    innovation=('把可编辑地图连接位置与运行比较，再将设计词典序首分歧、独立评价反转、基线差与四指标帕累托关系显示给用户。高峰三候选未达研究目标时明确提示不推荐采用，形成输入、候选比较、人工决策与证据导出的可追溯流程。A*、帕累托及相对运动为已有方法，创新定位为可解释决策与工程集成。')
    value=('用于园区配送前期方案讨论和教学：正常样本可说明时效与暴露取舍，高峰样本可支持暂缓采用全部候选。研究目标可调，诊断不替代人工偏好，也不保证扩容有效。应用前仍需核实尺度、楼高、需求、场地和运行规则，补充动力学、能耗与实地验证。')
    assert len(description)<=300 and len(innovation)<=200 and len(value)<=200
    return content,description,innovation,value
