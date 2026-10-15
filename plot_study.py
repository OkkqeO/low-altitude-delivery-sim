"""Optional Matplotlib figures for the paired study. Core app needs no packages."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description="生成多机错峰配对实验图表")
    parser.add_argument("--input",type=Path,default=Path(__file__).resolve().parent/"results"/"safety")
    args=parser.parse_args()
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        import numpy as np
    except ImportError as error:
        raise SystemExit("图表依赖未安装：python -m pip install -r requirements-analysis.txt") from error
    font=Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"]=font_manager.FontProperties(fname=str(font)).get_name()
    else:
        plt.rcParams["font.sans-serif"]=["Noto Sans CJK SC","Microsoft YaHei","DejaVu Sans"]
    plt.rcParams.update({"axes.unicode_minus":False,"font.size":11,"axes.spines.top":False,
                         "axes.spines.right":False,"pdf.fonttype":42})
    rows=list(csv.DictReader((args.input/"summary.csv").open(encoding="utf-8-sig")))
    index={(r["scenario"],r["plan"],r["dispatch"]):r for r in rows}
    keys=[(s,p) for s in ("normal","peak","closure") for p in ("fixed","distance","combined")]
    labels=[{"normal":"正常","peak":"高峰","closure":"关闭"}[s]+"\n"+{"fixed":"固定","distance":"距离","combined":"综合"}[p] for s,p in keys]
    panels=[("air_conflict_count","间距不足事件 / 次",1),("mean_delivery","平均配送时间 / 秒",1),
            ("mean_exposure","每单人员暴露代理指数",1),("on_time_rate","订单准时率 / %",100)]
    fig,axes=plt.subplots(2,2,figsize=(16,10),layout="constrained")
    x=np.arange(len(keys))
    for ax,(metric,title,factor) in zip(axes.flat,panels):
        for mode,offset,label,color in (("baseline",-.19,"基线调度","#899bb2"),("staggered",.19,"错峰起飞","#087f8c")):
            means=np.array([float(index[(*key,mode)][metric+"_mean"] or "nan")*factor for key in keys])
            stds=np.array([float(index[(*key,mode)][metric+"_std"] or "nan")*factor for key in keys])
            ax.bar(x+offset,means,width=.36,color=color,label=label,yerr=stds,capsize=3,
                   error_kw={"elinewidth":1,"ecolor":"#35445a"},zorder=3)
            if metric=="air_conflict_count" and mode=="staggered":
                for px,value in zip(x+offset,means):
                    if value==0:
                        ax.text(px,.45,"0",ha="center",va="bottom",fontsize=9,color=color)
        ax.set_title(title,loc="left",pad=14,fontweight="bold")
        ax.set_xticks(x,labels)
        ax.set_axisbelow(True)
        ax.grid(axis="y",alpha=.22)
        ax.set_ylim(bottom=0)
        if metric=="on_time_rate":
            ax.set_ylim(0,110)
    handles,legend_labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,legend_labels,loc="outside upper right",ncol=2,frameon=False)
    fig.suptitle("多机间距约束与配送效率的权衡",fontsize=20,fontweight="bold")
    fig.supxlabel("模拟园区；每场景5个评价种子，误差线为样本标准差；两种调度使用相同场站与订单。",fontsize=11)
    fig.savefig(args.input/"多机错峰实验对比.png",dpi=180)
    fig.savefig(args.input/"多机错峰实验对比.pdf")
    plt.close(fig)
    (args.input/"plot_metadata.json").write_text(json.dumps({"matplotlib":matplotlib.__version__,
        "numpy":np.__version__,"summary_sha256":hashlib.sha256((args.input/"summary.csv").read_bytes()).hexdigest(),
        "error_bars":"sample standard deviation across evaluation seeds"},indent=2),encoding="utf-8")
    print(f"PNG/PDF saved: {args.input}")


if __name__=="__main__":
    main()
