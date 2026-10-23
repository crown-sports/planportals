# PlanPortals

按门连接房间，再检查关掉一扇门后，哪些房间到不了了。

[English](README.md) · [v0.2.1](https://github.com/crown-sports/planportals/releases/tag/v0.2.1)

![关闭客厅与厨房之间的门后，厨房和书房变为不可达；卫生间前后均为灰色](examples/workflow.png)

生成示例：关闭客厅—厨房的门后，从卧室出发到不了**厨房和书房**；灰色卫生间原本就不可达。[运行这张示例](docs/workflow.zh-CN.md)。

## 先跑起来

Python 3.10+，不需要 GPU、模型或云服务。

```bash
python -m pip install "git+https://github.com/crown-sports/planportals.git@v0.2.1"
planportals demo --output runs/demo
planportals access --graph runs/demo/portals.json --from-room bedroom \
  --blocked-openings door-living-kitchen --output runs/access.json \
  --fail-on-newly-isolated
```

原始输入与结果请分开放；重复使用同一个输出目录，会替换其中生成的结果文件。

demo 提供五个房间和带类别的开口。打开 `runs/demo/portals.svg`，查看 **3 条被接受的门连接**。封门命令先写出 `access.json`，因新增两个不可达房间而退出 **1**，原始图和几何不会改变。

门 ID 从图的 decisions 中读取；ID 错误或输入不合法时退出 **2**。`route` 也支持 `--blocked-openings` 和 `--fail-if-unreachable`。

## 换成自己的房间和开口

```bash
planportals build --input /private/scene.json --output runs/result
```

提供房间多边形、墙段，以及标为门、窗或未知的开口。适配器可读取 [WallGraph](https://github.com/crown-sports/wallgraph) 墙线和 [PlanRegions](https://github.com/crown-sports/planregions) 房间输出，也支持对齐的语义标签图。[场景格式与 API](docs/api.md)。

门要有墙体支撑，两侧房间判断也要一致，才会成为连接。窗户和未知缺口不进入路线图；被拒绝或有歧义的候选会在 `portals.json` 保留原因。[查看候选到连接图的效果](examples/demo.png)。

## 怎么读结果

`access.json` 会分开列出“原本就不可达”和“这次封门后才不可达”的房间。路线是房间 ID 与开口 ID 的序列；图中的连线表示邻接，不是绕过家具的行走轨迹。

门的类别由上游提供，仓库没有附带检测器。上游标错类别，仍可能产生错误连接。几何开口宽度不是已核实的门净宽；路线报告不替代无障碍或疏散评估。[生成案例与失败情况](docs/validation.md)。

## 四个库一起用

[完整示例](docs/workflow.zh-CN.md)从同一张生成户型图得到墙线、房间、面积、缺墙前后对照和封门报告。脚本从**当前 main 源码**获取，依赖引擎按指南安装已发布 tag。

## 继续看

[实现说明](docs/product.md) · [API](docs/api.md) · [方法](docs/methods.md) · [架构](docs/architecture.md)

[贡献](CONTRIBUTING.md) · [发布检查](docs/releasing.md) · [安全报告](SECURITY.md)

代码与原创生成图使用 MIT 许可，不包含真实图纸、标注、数据集或模型权重。[来源说明](NOTICE.md)。
