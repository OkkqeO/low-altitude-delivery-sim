"""Export case figures with Matplotlib; simulation outputs are read unchanged."""
import csv
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT/"cases/user_map_300m"
OUTPUT = ROOT/"results/user_map_300m"
font = Path("C:/Windows/Fonts/msyh.ttc")
if font.exists():
    font_manager.fontManager.addfont(str(font))
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
plt.rcParams.update({"font.size":10,"axes.unicode_minus":False,"axes.spines.top":False,
                     "axes.spines.right":False,"svg.fonttype":"none"})
COLORS={"fixed":"#7c8798","distance":"#3369d1","combined":"#087f79"}
NAMES={"fixed":"固定位置","distance":"距离优先","combined":"运行优选"}


def map_figure():
    scene=json.loads((CASE/"scene.json").read_text(encoding="utf-8"))
    snapshot=OUTPUT/"studies/h30_d5.json.gz"
    if snapshot.exists():
        study=json.loads(gzip.decompress(snapshot.read_bytes()).decode("utf-8"))
    else:
        study=json.loads((OUTPUT/"h30_d5/study.json").read_text(encoding="utf-8"))
    result=next(r for r in study["results"] if r["config"]["scenario"]=="peak")
    plan=result["plans"]["combined"]
    fig,axes=plt.subplots(1,2,figsize=(11,8.5))
    fig.subplots_adjust(left=.07,right=.98,bottom=.13,top=.88,wspace=.19)
    width,height=scene["width"],scene["height"]
    axes[0].imshow(Image.open(CASE/"original.jpg"),extent=(0,width,height,0))
    for i,ax in enumerate(axes):
        ax.set_xlim(0,width)
        ax.set_ylim(height,0)
        ax.set_aspect("equal")
        ax.set_xlabel("横向距离 / 米")
        ax.set_ylabel("纵向距离 / 米")
        ax.set_facecolor("#f5f3ec")
        for b in scene["buildings"]:
            ax.add_patch(Rectangle((b["x"],b["y"]),b["w"],b["h"],
                                  facecolor="#b7c4d0" if i else "none",edgecolor="#9b5b43" if not i else "#8999aa",
                                  lw=.8,alpha=.95 if i else .8))
        if i:
            for pad_id in plan["pad_ids"]:
                for d in scene["deliveries"]:
                    route=result["routes"].get(f"{pad_id}:{d['id']}")
                    if route:
                        ax.plot(*zip(*route["points"]),color=COLORS["combined"],lw=1,alpha=.46,zorder=2)
        for d in scene["deliveries"]:
            ax.scatter(d["x"],d["y"],s=24,marker="D",color="#b9621f",edgecolor="white",lw=.5,zorder=4)
            ax.annotate(d["id"],(d["x"],d["y"]),xytext=(4,3),textcoords="offset points",fontsize=7,color="#8a4316",zorder=5)
        for p in scene["pads"]:
            selected=i and p["id"] in plan["pad_ids"]
            ax.scatter(p["x"],p["y"],s=100 if selected else 38,color=COLORS["combined"] if selected else "white",
                       edgecolor="#1763ac",lw=1.1,zorder=5)
            ax.annotate(p["id"],(p["x"],p["y"]),xytext=(6,-10),textcoords="offset points",fontsize=8,color="#17518b",zorder=6)
        ax.plot([12,62],[height-12,height-12],color="#25364c",lw=2)
        ax.text(37,height-17,"50米",ha="center",fontsize=8,color="#25364c")
    axes[0].set_title("原始真实地图与人工近似轮廓",loc="left",fontsize=12,pad=10)
    axes[1].set_title("30米保守绕楼情景 · 5架机",loc="left",fontsize=12,pad=10)
    fig.suptitle("300米真实地图截图：起飞点优选试跑",fontsize=17,fontweight="bold",y=.965)
    fig.text(.5,.917,f"运行优选：{plan['configuration_label']}  |  6个候选点 · 10个模拟配送点",ha="center",fontsize=10,color="#43536a")
    fig.text(.06,.073,"圆点S为候选起飞点，菱形D为模拟配送点；右图实心圆为选中起飞点，绿色线为候选航路。",fontsize=9)
    fig.text(.06,.045,"宽度由用户提供；楼高采用30米上界；点位、订单与人流为假设。原图蓝色定位标记不参与建模。",fontsize=9,color="#58667a")
    fig.savefig(OUTPUT/"地图与选址.png",dpi=160)
    fig.savefig(OUTPUT/"地图与选址.svg")
    plt.close(fig)


def capacity_figure():
    rows=list(csv.DictReader((OUTPUT/"summary.csv").open(encoding="utf-8-sig")))
    index={(int(r["altitude"]),int(r["drone_count"]),r["scenario"],r["plan"]):r for r in rows}
    fig,axes=plt.subplots(2,3,figsize=(13,8))
    fig.subplots_adjust(left=.07,right=.98,bottom=.15,top=.84,hspace=.42,wspace=.30)
    columns=[("on_time_rate",100,"高峰准时率 / %"),("mean_delivery",1,"高峰平均配送 / 秒"),
             ("mean_airspace_delay",1,"高峰额外错峰等待 / 秒")]
    for row,altitude in enumerate((30,45)):
        for col,(metric,factor,title) in enumerate(columns):
            ax=axes[row,col]
            for key in NAMES:
                group=[index[altitude,n,"peak",key] for n in (3,5,8)]
                means=[float(r[metric])*factor for r in group]
                stds=[float(r[metric+"_std"])*factor for r in group]
                ax.errorbar([3,5,8],means,yerr=stds,color=COLORS[key],label=NAMES[key],marker="o",lw=1.8,capsize=3,ms=4)
            ax.set_title(f"{altitude}米巡航 · {title}",loc="left",fontsize=10)
            ax.set_xticks([3,5,8])
            ax.set_xlabel("无人机数量 / 架")
            ax.set_ylim(bottom=0)
            if metric=="on_time_rate":
                ax.set_ylim(-2,105)
            ax.grid(axis="y",alpha=.18)
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="upper center",bbox_to_anchor=(.52,.91),ncol=3,frameon=False)
    fig.suptitle("真实地图空间下的高峰容量测试",fontsize=18,fontweight="bold",y=.98)
    fig.text(.06,.075,"每个配置：3个设计种子、5个独立评价种子；同一高度和机队内各方案使用相同需求与资源。",fontsize=10)
    fig.text(.06,.045,"误差线为样本标准差；楼高按30米上界建模，30米需绕楼、45米可越楼。模型输出不代表实测运营。",fontsize=10,color="#58667a")
    fig.savefig(OUTPUT/"高峰容量对比.png",dpi=160)
    fig.savefig(OUTPUT/"高峰容量对比.svg")
    plt.close(fig)


if __name__=="__main__":
    map_figure()
    capacity_figure()
    print(OUTPUT/"地图与选址.png")
    print(OUTPUT/"高峰容量对比.png")
