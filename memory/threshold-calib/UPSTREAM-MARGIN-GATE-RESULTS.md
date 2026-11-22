# 上游方案一（双档余量）：用官方探针和门禁直接测

2026-11-22。此前方案一的数都是回放上游已提交的记录得来的，没有人带着新开关跑过探针。这一轮用打了补丁的插件检出、官方的 `tools/provenance_probe.py` 和 `tools/mcnemar_gate.py` 直接跑，向量模型是本地 bge-m3。

**在 bge-m3 上四条门禁没有一种设置能同时通过。** 方案一（静默 0.7、已有结果 0.5）增益显著，但噪声上涨。把静默那一半收紧到不涨噪声，救回只剩 4 题，不显著。

| 静默时的余量（已有结果时都是 0.5） | 命中@5 | 救回 / 丢失 | p | 噪声 | 混淆 | 没过的条件 |
|---:|---:|---:|---:|---:|---:|---|
| 0.7（方案一） | 480 → 487 | 7 / 0 | 0.016 | 93 → 95 | 34 → 34 | 噪声 |
| 0.8 | 480 → 485 | 5 / 0 | 0.0625 | 93 → 94 | 34 → 34 | 噪声、显著性 |
| 0.9 | 480 → 484 | 4 / 0 | 0.125 | 93 → 93 | 34 → 34 | 显著性 |
| 1.0（只在已有结果时放宽） | 480 → 484 | 4 / 0 | 0.125 | 93 → 93 | 34 → 34 | 显著性 |

上表是原来题池的五个题集，540 道真问题。四种设置都没有丢目标。

## 和回放的结论对照

| | 回放上游已提交的记录 | 这一轮，bge-m3 |
|---|---|---|
| 默认余量的命中 | 481 / 540 | 480 / 540 |
| 方案一的救回 / 丢失 | 5 / 0，p = 0.0625 | 7 / 0，p = 0.016 |
| 方案一的噪声 | 94 → 94 | 93 → 95 |
| 方案一的混淆 | 34 → 34 | 34 → 34 |
| 没过的条件 | 显著性 | 噪声 |

两个模型的起点几乎一样，卡住的条件不一样。方案一「噪声不变」的结论依赖模型。

多出来的两行噪声是 `contrast_ru` 的 `c17` 和 `c31`，都是本来静默的闲聊。上游当初把余量全部放到 0.5 时翻掉的四行里也有这两行，换成 bge-m3 后它们在 0.7 和 0.8 就进来了。

救回和噪声是同一个开关放进来的。0.7 比 1.0 多救回的 3 题（`multi/nl 18`、`contrast_zh p4q0`、`household/zh q065`）都是本来静默的一轮；多出来的噪声也是。`c31` 在 0.8 就进来，早于其中两道题，所以静默余量没有一个中间值能只要救回、不要噪声。

## 把题池加大

加上 household 的 dev 部分和 `synthetic_zh`（不带关键词，和其余题集同一种跑法），共 696 道真问题。

| 静默时的余量 | 命中@5 | 救回 / 丢失 | p | 噪声 | 混淆 | 没过的条件 |
|---:|---:|---:|---:|---:|---:|---|
| 0.7（方案一） | 565 → 576 | 11 / 0 | 0.001 | 142 → 145 | 46 → 47 | 噪声、混淆 |
| 0.8 | 565 → 573 | 8 / 0 | 0.008 | 142 → 144 | 46 → 47 | 噪声、混淆 |
| 0.9 | 565 → 570 | 5 / 0 | 0.0625 | 142 → 142 | 46 → 47 | 混淆、显著性 |
| 1.0 | 565 → 569 | 4 / 0 | 0.125 | 142 → 142 | 46 → 46 | 显著性 |

加题确实带来更多救回（多出来的部分贡献 4 题），但也带来 1 行噪声（`household/ru h022`）和 1 行混淆。只在已有结果时放宽的那一种，加题后一道也没多救回。

`synthetic_zh` 带关键词（#95 的跑法）单独看：方案一 29 → 30，噪声 3 → 3，混淆 10 → 12；只在已有结果时放宽是 29 → 29，混淆同样 10 → 12。

## 测量方法

- 插件检出是 `vendor/holo-margin/plugin`，0.30.1 加上 `docs/upstream-memory-review/patches/holo-4-recall-margin-shown.patch`。探针参数 `--emb on --modes off --repeats 1`，每种设置一个目录下的一组文件。`multi` 用上游已提交记录里的全部 18 种语言，household 的 test 和 dev 分开跑。
- 探针通过 `EMB_URL` 和 `EMB_MODEL` 读向量接口。接口是只监听本机的 [embed_endpoint.py](embed_endpoint.py)，用 `vendor/models/bge-m3`（CUDA fp16，只从本地文件加载，权重 SHA-256 与 `local_models.py` 固定的值一致）。每一行记下的 `emb_model` 都是这个接口。
- Hermes 核心用提交 `e8a31a1` 里的 `memory/keyword-gate/core_shim`，`HERMES_HOME` 指向项目内的沙盒目录。
- 0.7、0.8、0.9 三种设置由官方的 `mcnemar_gate.py --pair margin` 直接出结论。静默 1.0 的那一种两边余量相同，打过补丁的官方脚本会拒绝这种配对，所以用 [calib_margin_gate.py](calib_margin_gate.py)：噪声、混淆和 p 调用上游脚本自己的函数，只有两边的配对在这里做。它在 0.7 那一组文件上和官方脚本逐项一致（7 / 0，p = 0.0156，噪声 93 → 95，混淆 34 → 34）。
- 计数在 [upstream-margin-gate-results.json](upstream-margin-gate-results.json)。

## 限制

- 模型是 bge-m3，不是上游已提交记录用的模型。上游的模型在同一个提交、带新开关时是什么结果，仍然没有人测过。
- 静默余量 0.8 和 0.9 是看过 0.7 的结果后补扫的。
- 各题集之间不独立：household 的 dev 和 test 共用同一批事实，三个语言是同一批题的翻译。
- 探针在每组运行里重新建库并向量化，没有复用上游提交记录里的向量。

## 复现

Python 3.11.4、NumPy 1.26.4、PyTorch 2.11.0、sentence-transformers 5.5.0、snowballstemmer 3.1.1。先起本机接口，再在插件检出目录里跑探针。`$CoreDir` 是提交 `e8a31a1` 里的 `memory/keyword-gate/core_shim`，`$Rows` 是放结果的目录，`$Home` 是一个空的沙盒目录。

```powershell
python -E -B memory/threshold-calib/embed_endpoint.py vendor/models/bge-m3 12371

$env:HERMES_HOME=$Home; $env:HERMES_AGENT_REPO=$CoreDir
$env:EMB_URL='http://127.0.0.1:12371/v1'; $env:EMB_MODEL='bge-m3'
cd vendor/holo-margin/plugin
$Common='--emb','on','--modes','off','--repeats','1','--out',$Rows
$Langs='ar,bn,de,en,es,fr,hi,id,it,ja,ko,nl,pl,pt,ru,th,tr,zh'
# 每种设置各跑一遍下面七条；$Arm 依次取四种：
#   --recall-margin 1.0
#   --recall-margin 0.7 --recall-margin-shown 0.5
#   --recall-margin 0.8 --recall-margin-shown 0.5   （0.9 同理）
#   --recall-margin 1.0 --recall-margin-shown 0.5
python -B tools/provenance_probe.py @Common --set multi --langs $Langs @Arm
python -B tools/provenance_probe.py @Common --set contrast_en @Arm
python -B tools/provenance_probe.py @Common --set contrast_ru @Arm
python -B tools/provenance_probe.py @Common --set contrast_zh @Arm
python -B tools/provenance_probe.py @Common --set household --split test @Arm
python -B tools/provenance_probe.py @Common --set household --split dev @Arm
python -B tools/provenance_probe.py @Common --set synthetic_zh @Arm

python -B tools/mcnemar_gate.py --pair margin <同一题集的两个文件，可以给多组>
cd ../../..
python -E -B memory/threshold-calib/calib_margin_gate.py --gate vendor/holo-margin/plugin/tools/mcnemar_gate.py --rows $Rows --arm _m1.0_s0.5 --sets multi contrast_en contrast_ru contrast_zh household_test
```

## 建议和后续

**要不要做**

- Issue D 现在不要按原样发。草稿写的是「噪声、混淆不变，差一道题」，那是上游模型上的回放。换成 bge-m3 后噪声涨了 2 行，这个结果应当写进去，否则维护者自己一测就会看到。
- 方案一能不能过门禁，取决于上游的模型上实际跑出来的数，这一步需要云端接口，见下。

**要做的话改哪里**

- 如果上游模型上的结果和 bge-m3 一样（噪声上涨），可提的只剩「只在已有结果时放宽」这一种：噪声行按构造不会增加，bge-m3 上救回 4 题、不显著。它是否值得提，由你定。
- 提这一种还要改补丁里的门禁脚本：现在它拒绝「两边余量相同、只有第二个余量不同」的配对。补丁在 `docs/upstream-memory-review/patches/`，本轮没有动。

**还需要谁跑什么**

需要在上游已提交记录所用的模型上，用同一套命令跑一遍。那需要云端向量接口，本轮没有调用。必跑的是三种设置（默认、方案一、只在已有结果时放宽），合计约 3,200 条问题。问题部分每种设置约 8,500 token，是按本轮的输出算的；事实部分没有逐条算，估计是同一量级。按 text-embedding-3-small 的标价 0.02 美元每百万 token，合计不到 0.01 美元。只发送上游公开的测试数据。给 Codex 的提示词在本轮的对话里。
