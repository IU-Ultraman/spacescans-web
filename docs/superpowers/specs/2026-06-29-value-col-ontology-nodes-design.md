# Outcome (value_col) Ontology Nodes — Design

**Date:** 2026-06-29
**Status:** Approved (brainstorming complete)
**Scope owner:** spacescans-web

## Goal

把 9 个变量各自的 **outcomes(value_cols,result.csv 里真正算出来的列,如 cbp 的 `r_religious`、noise 的 `l50dba_exi`)** 作为**子节点**收进 SPACESCANS 本体,挂在各变量的 ontology 节点下,每个带人类可读定义。这样在 `/catalog` 展开某个暴露就能看到它的全部 outcome + 定义,也为后续结果页"列名→含义"打基础。

承接前序:这等于用"做成本体节点"这条路解决最初 grill 的 scope#1(结果页列名看不懂)。

## 已锁定决策

1. 全部 ~32 个 value_col 都做成子本体节点(选项 A)。
2. 定义来源:
   - **xlsx `data_full/ExposomeVariablesList.xlsx`** 覆盖的 4 个变量(权威):cbp_zcta5(CBP sheet)、fara_tract(USDA FARA sheet)、ndi(ACS sheet)、walkability(National Walkability Index sheet)。**在 brainstorming 阶段已从 xlsx 抽取并固化进脚本**(extend_ontology 运行时不依赖该 xlsx,它在 data_full/、不在 web 仓库)。
   - **variable_metadata.json description** 覆盖的 5 个变量:noise、vnl、temis、nhd_bluespace、tiger_proximity。
3. `noise` 的 `l50dba_imp` / `l50dba_nat`:SPACEO/xlsx 都没明确,定义写 "alternative-scenario daytime L50 transportation-noise surface (dBA); exact scenario pending verification against the BTS source"。
4. 只做现有 9 个变量的 outcome;**不**扩展到 xlsx 里那些尚未接入 web 的数据源(ACAG/CACES/EPA NATA/US HUD/UCR 等)。

## 设计

### A. value_col 节点(共 32),挂到各变量节点下

每个节点:`id = SPACESCANS_VC_<col>`(全 32 个 col 名互不重复,前缀确保不与 SPACEO/已有 SPACESCANS_ 节点冲突)、`label`(简短人读名)、`definition`(下表)、`parent = 变量的 ontology 节点`。

**父节点 → 其 value_col 子节点(定义来源)**:

| 变量 | 变量节点 id | value_col 子节点 | 定义源 |
| --- | --- | --- | --- |
| cbp_zcta5 | `SPACESCANS_Community_Organization_Density` | r_religious, r_civic, r_business, r_political, r_professional, r_labor, r_bowling, r_recreational, r_golf, r_sports (10) | xlsx CBP("Number of establishments in <X> per 10000 population") |
| fara_tract | `000294` (Food_Access_Exposome) | LILATracts_1And10, LATracts1, HUNVFlag, LowIncomeTracts (4) | xlsx USDA FARA |
| ndi | `SPACESCANS_Neighborhood_Deprivation_Index` | ndi (1) | xlsx ACS ("Neighborhood Deprivation Index") |
| walkability | `SPACESCANS_Walkability` | NatWalkInd (1) | xlsx Walkability ("Relative walkability") |
| noise | `000289` (Noise) | l50dba_exi, l50dba_imp, l50dba_nat (3) | variable_metadata (imp/nat: pending-verification note) |
| vnl | `000290` (Light_at_Night) | value (1) | variable_metadata (annual mean radiance nW/cm²/sr) |
| temis | `000288` (Ultraviolet_Radiation) | uvddc, uvdec, uvdvc, uvief (4) | variable_metadata (DNA-damage / erythemal / vitamin-D daily dose; UV index at noon) |
| nhd_bluespace | `SPACESCANS_Bluespace` | dist_flow_m, dist_water_m, dist_area_m, dist_coast_m, dist_blue_m (5) | variable_metadata (distance m to flowline/waterbody/area/coastline[99999 inland]/combined) |
| tiger_proximity | `SPACESCANS_Road_Proximity` | dist_pri, dist_sec, dist_prisec (3) | variable_metadata (distance m to primary S1100 / secondary S1200 / combined) |

`definition` 末尾统一附 "(Result column: <col>.)" 以便从结果列名反查。`label` 用简短人读名(如 r_religious → "Religious organizations";l50dba_exi → "Noise — existing conditions")。

### B. has_children 翻转(泛化)

加入子节点后,**这 9 个变量节点都从叶子变父节点**,需把它们在各自父(域)节点 child-list 文件里的 `has_children` 置 true:

| 变量节点 | 所在 child-list 文件(域) |
| --- | --- |
| 000289 / 000290 / 000288 / SPACESCANS_Bluespace | `nodes/000094_2.json` (Natural) |
| 000294 / SPACESCANS_Walkability / SPACESCANS_Road_Proximity | `nodes/000292.json` (Built) |
| SPACESCANS_Neighborhood_Deprivation_Index / SPACESCANS_Community_Organization_Density | `nodes/000295.json` (Social) |

现有脚本只翻 000295(在 000093_2.json),需泛化成:对每个获得 value_col 子节点的变量节点,在其域文件里把对应条目的 `has_children` 置 true。用一个 `VAR_NODE_TO_DOMAIN_FILE` 映射实现。

### C. 脚本改动 `backend/scripts/extend_ontology.py`

- 新增 `VALUE_COL_NODES`:列表,每项 `{col, parent, label, definition}`(parent = 变量节点 id)。32 项,定义已固化(来源见上)。
- 复用现有节点注入逻辑(metadata / search-index refresh-or-append / 父 child-list 文件 create-or-append + 按 label 排序),对 VALUE_COL_NODES 同样处理:
  - 每个 value_col 节点写入 metadata + search-index;
  - 追加到其 parent(变量节点)的 `nodes/<parent>.json`(不存在则创建——4 个 SPACEO 叶子 000289/000290/000288/000294 此前无 child-list 文件,会新建);
  - 把该 parent 在其域文件里的 `has_children` 置 true(泛化的 flip)。
- 幂等:以 id 判存 + refresh-in-place,可反复跑。
- 保持现有 5 个 `SPACESCANS_*` 变量节点的注入不变。

### D. 测试 `backend/tests/test_extend_ontology.py`

- 扩充 fixture:父节点 child-list 文件需含 4 个 SPACEO 叶子(000289/000290/000288/000294)条目(目前 fixture 只有 000294/000289 等部分)。
- 断言:(a) 抽样 value_col 节点(如 r_religious 在 SPACESCANS_Community_Organization_Density 下、l50dba_exi 在 000289 下)出现在对应 `nodes/<var>.json` + metadata + search-index;(b) 9 个变量节点的 `has_children` 在其域文件里为 true;(c) 幂等(再跑无重复、字节一致);(d) child-list 仍按 label 排序;(e) value_col 节点定义末尾含 "(Result column: <col>.)"。

### E. 应用到真实 ontology + 提交产物

跑 `python scripts/extend_ontology.py` 重新生成 `frontend/public/ontology/{metadata,search-index}.json` + 受影响的 `nodes/*.json`(新增 9 个变量节点的 child-list 文件、更新 3 个域文件的 has_children),提交。

## Out of scope

- 结果页/向导里用这些定义渲染列名(后续 value_col_meta 那一项;本 spec 只把数据进 ontology,`/catalog` 展开即可见)。
- xlsx 里尚未接入 web 的其它数据源(ACAG/CACES/NATA/HUD/UCR…)。
- 改 SPACEO 源 OWL(同前:OWL 不在仓库;这些是 SPACESCANS-local 扩展,靠 id 前缀标识)。

## Files touched

- Modify `backend/scripts/extend_ontology.py`(VALUE_COL_NODES + 泛化 has_children flip)
- Modify `backend/tests/test_extend_ontology.py`(value_col 断言 + fixture)
- Modify `frontend/public/ontology/{metadata.json, search-index.json}` + `nodes/*.json`(脚本重新生成的产物:9 个新 child-list 文件 + 3 个域文件 has_children)
