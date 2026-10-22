# 同一张平面图：测量、结构变化与封门复核

[English](workflow.md) · [返回 PlanPortals](../README.zh-CN.md)

这个例子把同一张生成户型依次交给四个库：提取墙线、测量房间、移除一段隔墙，再关掉一扇门。墙体边界、六条尺寸和门窗类别均为提供的标注，不涉及真实图纸、OCR 或识别模型。

## 从哪个库开始

平时只安装需要的库；下面的完整示例才安装四个。

| 已有输入 → 下一步判断 | 从这里开始 | 需要时交给 |
| --- | --- | --- |
| 二值墙体掩码 → 可选中的墙线和节点 | [WallGraph](https://github.com/crown-sports/wallgraph) | 掩码给 PlanRegions，路径给 PlanMetric/PlanPortals |
| 墙体掩码或两版实例图 → 房间提取、合并/拆分复核 | [PlanRegions](https://github.com/crown-sports/planregions) | 精确像素面积给 PlanMetric，多边形给 PlanPortals |
| 像素几何 + 尺寸观测 → 有依据的长度和面积 | [PlanMetric](https://github.com/crown-sports/planmetric) | 接受的比例尺供测量界面或开口宽度条件使用 |
| 房间 + 墙线 + 带类别开口 → 连通性与封门影响 | [PlanPortals](https://github.com/crown-sports/planportals) | 在自己的应用中复核房间和开口序列 |

只有未标注的扫描图时，四库尚不能构成完整识别器。先获得可复核的墙体掩码、尺寸观测和门窗候选；通用视觉模型可以提供候选，但仍需明确坐标、来源及拒绝条件。

## 跑通一次

需要 Python 3.10+。克隆当前 main 源码以获取示例脚本；这个新脚本不在已有 v0.2.0 发布资产中。四个计算库固定到已有发布版本。安装会下载依赖，不下载模型权重。

```bash
git clone https://github.com/crown-sports/planportals.git
cd planportals
python -m venv .venv
source .venv/bin/activate
python -m pip install \
  "git+https://github.com/crown-sports/wallgraph.git@v0.2.0" \
  "git+https://github.com/crown-sports/planregions.git@v0.4.0" \
  "git+https://github.com/crown-sports/planmetric.git@v0.2.0" \
  "git+https://github.com/crown-sports/planportals.git@v0.2.0"
python tools/review_workflow.py --output runs/review
```

Windows 使用 `.venv\Scripts\activate` 激活。安装后本地运行。输出目录必须是新目录；重复使用旧目录返回错误，避免覆盖上次复核结果。

预期 `summary.json`：**5 个区域**、横纵均 **10 毫米/像素**、**3 条有效门连接**。客厅按实例像素计数、扣除墙体像素后得到 **14.3221 平方米**。刻意删除一段分隔墙后，区域 **5 → 4**，出现 **1 个合并组**。从卧室（区域 `3`）出发，关闭 `door-living-kitchen` 后新隔离的是 **厨房和书房**；浴室原本不可达，不计入“新增隔离”。

| 查看输出 | 应检查什么 |
| --- | --- |
| `runs/review/walls/walls.svg` 与 `walls.json` | 由提供的墙体掩码得到的中心线和节点 |
| `runs/review/regions/regions.png` 与 `regions.json` | 同一 1200×800 像素坐标中的五个区域 |
| `runs/review/calibration/evidence.svg`、`measurements.json` | 六条尺寸、横纵比例尺与像素面积换算 |
| `runs/review/wall-measurements.json` | 中心线路径长度，不是墙面工程量 |
| `runs/review/changes.html` | 缺失分隔墙后客厅与厨房合并的证据 |
| `runs/review/portals/portals.svg`、`access.json` | 门的采用记录、窗/未知开口排除、封门后可达性 |

用于房间分区的掩码刻意保留连续分隔边界，包括标注门的位置；这不表示实体门是实墙。“缺失分隔墙”和“临时关门”是两个独立场景，不会偷偷改写彼此的输入证据。

## 复用输出并识别拒绝

使用已发布 CLI 重新测量：

```bash
planmetric measure --observations runs/review/observations.json \
  --geometry runs/review/regions/regions.json --output runs/review/measured-again.json
```

预期退出码 **0**，面积与示例相同。比例尺未通过、原图尺寸不一致时应修正输入，不能把拒绝转换成猜测的比例尺。

分别执行两种复核门禁：

```bash
planregions compare --before runs/review/regions/labels.npz \
  --after runs/review/changed-regions/labels.npz \
  --output runs/review/change-gate.json --fail-on merge
planportals access --graph runs/review/portals/portals.json --from-room 3 \
  --blocked-openings door-living-kitchen --output runs/review/access-gate.json \
  --fail-on-newly-isolated
```

两条命令都先写报告，再按预期返回 **1**：分别发现区域合并与两个新增隔离房间。退出码 1 是需要复核的结果。门 ID 不存在或输入无效返回 **2**。

完整脚本也支持 `--fail-on-newly-isolated`，写完结果后返回 1。改用 `--blocked-opening no-such-door` 和新的输出路径，会返回 2 且不创建结果目录。

## 接入自己的图纸

用已复核的二值掩码替代生成墙体；用 OCR/人工复核结果替代尺寸观测；用带类别的检测结果替代开口标注。它们必须使用**同一原图坐标**，保留来源与拒绝记录。脚本是可检查的集成示例，不是任意图纸的批量导入器。

区域变化不自动等于识别错误；尺寸共识不能证明全部尺寸真实；房间路线也不等于避障路径或疏散认证。各库 `docs/product.md` 说明几何处理方式，并链接对应实现。
