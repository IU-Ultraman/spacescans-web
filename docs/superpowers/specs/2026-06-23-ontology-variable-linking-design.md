# Ontology ↔ Variable Linking + Ontology Extension — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorming complete)
**Scope owner:** spacescans-web

## Goal

把 web app 里那 9 个可选暴露变量(`variable_metadata.json`)和 SPACESCANS 本体(`/catalog` 浏览的那棵树)**真正链接起来**:每个变量带上一个本体节点 id。其中 4 个变量直接连现有节点;5 个本体里没有对应概念的变量,**通过扩展本体新增 5 个节点**来补上。

这是更大目标(让"懂科研、不懂本工具的研究者"易懂地使用本站)的**第 1 个子项**;其余 3 项(边界类型解释、buffer/raster 大白话、进度步骤友好名)以及暴露列 `value_col_meta` 标签是**独立子项,不在本 spec 内**。

## Background / 现状(已核实)

- `/catalog` 页面的本体数据是 `frontend/public/ontology/{index,metadata,search-index}.json` + `nodes/<parentId>.json`,由 `backend/scripts/build_ontology.py` 从一个 OWL 源(`ontology files/SPACEO_20251203.owl`,SPAtial and Contextual Exposome Ontology)用 `owlready2` 生成。
- **OWL 源文件当前不在磁盘上、从未提交、也未 gitignore**;仓库里只有生成出来的 JSON 产物(commit `5bca9b4`)。整个本体 1859 个节点里 **1784 个本就是无上游 IRI 的自定义节点**,只有 73 个来自 TEO(sbmi.uth.edu)、2 个来自 BFO(ifomis.org)——即本体绝大部分已是 SPACESCANS 自建。
- `variable_metadata.json` 目前**没有任何**指向本体的字段(零链接)。
- 节点结构:`{id, label, definition, has_children}`。`index.json` 是顶层节点数组;`nodes/<parentId>.json` 是某父节点的**直接子节点数组**(每项同样是 `{id,label,definition,has_children}`);`metadata.json` 是 `{id: {id,label,definition}}` 全表;`search-index.json` 是 `[{id,label,definition}]` 列表。各处子节点数组按 `label` 升序排列(见 `build_ontology.py` 的 `.sort(key=lambda x: x["label"])`)。

## 已锁定的决策

1. **9 个变量全部链接**(不是只连干净命中的 4 个)。
2. **缺口靠扩展本体**补:新增 5 个节点,而非把变量硬挂粗父类。
3. **option C**:不动/不依赖 OWL 源(拿不到),改为写一个**幂等脚本直接改生成的 JSON**;新节点标注为 SPACESCANS-local 扩展、待并入 SPACEO。
4. **proximity 按领域归类**:Road_Proximity 挂 Built、Bluespace 挂 Natural(不挂 Access_Distance)。
5. 新节点 id 一律加前缀 `SPACESCANS_`,肉眼可辨是本地扩展。
6. `variable_metadata.json` 加**可选** `ontology_id` 字段,**不 bump `schema_version`**(只加可选属性,不触发前端 SchemaMismatchBanner)。

## 设计

### A. 5 个新本体节点

全部为 SPACESCANS-local 扩展;`definition` 末尾统一追加标记
` [SPACESCANS-local extension — pending merge into SPACEO]`。

| 新节点 id | label | 父节点 id (label) | definition(标记前的正文) |
|---|---|---|---|
| `SPACESCANS_Walkability` | Walkability | `000292` (Built_Environment_Exposome) | EPA National Walkability Index ranking neighborhoods on walkability characteristics such as intersection density, transit proximity, and employment mix. |
| `SPACESCANS_Neighborhood_Deprivation_Index` | Neighborhood_Deprivation_Index | `000295` (Social_Environment_Exposome) | Composite measure of neighborhood-level socioeconomic deprivation derived from US Census ACS variables. |
| `SPACESCANS_Community_Organization_Density` | Community_Organization_Density | `000295` (Social_Environment_Exposome) | Per-capita density of community organization categories (religious, civic, business, etc.) from US Census ZIP Business Patterns. |
| `SPACESCANS_Road_Proximity` | Road_Proximity | `000292` (Built_Environment_Exposome) | Distance from a residence to the nearest TIGER/Line primary, secondary, and combined primary+secondary roads. |
| `SPACESCANS_Bluespace` | Bluespace | `000094_2` (Natural_Environment_Exposome) | Distance from a residence to the nearest NHD surface-water feature (flowline, waterbody, area feature, coastline, and combined blue feature). |

注意:`000295` (Social_Environment_Exposome) 目前是**叶子**(无 `nodes/000295.json`)。加入 ndi/cbp 两个子节点后,需为它创建 `nodes/000295.json` 并把它在 `index.json`/`metadata`-派生处的 `has_children` 翻成 `true`。Built (`000292`) 和 Natural (`000094_2`) 已有子节点文件,追加即可。新节点自身均为叶子(`has_children=false`)。

### B. variable_metadata.json 的 9 条链接

给每个变量加可选 `ontology_id`:

| 变量 | ontology_id | 类型 |
|---|---|---|
| `noise` | `000289` (Noise) | 现有 |
| `vnl` | `000290` (Light_at_Night) | 现有 |
| `temis` | `000288` (Ultraviolet_Radiation) | 现有 |
| `fara_tract` | `000294` (Food_Access_Exposome) | 现有 |
| `walkability` | `SPACESCANS_Walkability` | 新增 |
| `ndi` | `SPACESCANS_Neighborhood_Deprivation_Index` | 新增 |
| `cbp_zcta5` | `SPACESCANS_Community_Organization_Density` | 新增 |
| `tiger_proximity` | `SPACESCANS_Road_Proximity` | 新增 |
| `nhd_bluespace` | `SPACESCANS_Bluespace` | 新增 |

### C. Schema 改动

`backend/app/data/variable_metadata.schema.json`:在变量对象的 `properties` 里加
```json
"ontology_id": { "type": "string", "minLength": 1 }
```
**不**加入 `required`(可选),`schema_version` 保持 `1`。后端 `variables.py` 的 `VariableMetadataModel` 加 `ontology_id: str | None = None`。前端 `VariableMetadata` 接口加 `ontology_id?: string`。

### D. 幂等扩展脚本 `backend/scripts/extend_ontology.py`

职责:把上面 5 个节点写进**已生成的** JSON 产物(默认目录 `frontend/public/ontology/`,可用 `--ontology-dir` 覆盖)。要求**幂等**——重复运行结果一致、不产生重复项。

具体步骤:
1. 载入 `metadata.json`、`search-index.json`、`index.json`、相关 `nodes/*.json`。
2. 对 5 个新节点,以 `id` 为键:
   - `metadata.json`:`metadata[id] = {id,label,definition}`(definition 已含扩展标记)。
   - `search-index.json`:若不存在该 `id` 则 append `{id,label,definition}`。
   - 父节点子列表 `nodes/<parentId>.json`:若不存在该 `id` 则 append `{id,label,definition,has_children:false}`,然后**按 label 升序重排**(与 `build_ontology.py` 一致);父文件不存在则新建(Social `000295` 即此情形)。
3. `has_children` 维护:`000295` (Social_Environment_Exposome) 不是顶层节点(不在 `index.json`),它的 `has_children` 标志只出现在其父 `000093_2` (Spatial_and_Contextual_Exposome) 的子列表文件 `nodes/000093_2.json` 里那一项上——把该项的 `has_children` 从 `false` 改成 `true` 即可。(`metadata.json` 不带 `has_children` 字段,无需改;Built `000292` / Natural `000094_2` 本来就有子节点,`has_children` 已是 `true`。)
4. 全程以 `id` 判存,保证可反复运行。
5. 完成后打印新增/已存在计数。

⚠️ **重建风险 + 缓解**:任何时候重跑 `build_ontology.py`(从 OWL 重生成 JSON)都会**覆盖掉**这 5 个节点。缓解:
- 在脚本顶部 docstring 和 `build_ontology.py` 末尾注释里**写明**:"从 OWL 重建后必须再跑一次 `extend_ontology.py`"。
- 不在本 spec 内自动链式调用(YAGNI;OWL 当前根本不在,重建不会发生);仅以文档约束。

### E. 前端呈现(Phase 2,本 spec 内但标为可选确认项)

数据链(A–D)是核心交付。让链接对研究者**可见**的最小做法:
- 在 `VariableCard` 上,当 `meta.ontology_id` 存在时显示一个 "View in ontology" 链接,deep-link 到 `/catalog?node=<ontology_id>`。
- 需要给 `/catalog` 页加上读取 `?node=` query 并预选/展开该节点的能力(`OntologyTree` 当前不支持按 id 定位展开——这是一处新增)。

Phase 2 比 Phase 1 重(涉及 catalog 树的 deep-link 展开)。**建议:本 spec 先只做 Phase 1(数据链 + 节点 + 脚本 + 测试),Phase 2 单独立项**,除非用户在 spec review 时要求一并做。

### F. 测试

- `backend/tests/test_extend_ontology.py`:
  - 在 tmp 目录放一份最小 ontology fixture(含 `000093_2`/`000094_2`/`000292`/`000295` 等父节点),跑 `extend_ontology` →
    - 断言 5 个新节点出现在 `metadata.json`、`search-index.json`、对应父 `nodes/*.json`;
    - 断言 `nodes/000295.json` 被创建且含 ndi/cbp 两项;`nodes/000093_2.json` 中 `000295` 项 `has_children==true`;
    - 断言**再跑一次**(幂等)各文件无重复、内容不变;
    - 断言子列表仍按 label 升序。
- `backend/tests/test_variable_registry.py`(已存在):加断言 `variable_metadata.json` 9 个变量都有合法 `ontology_id`,且每个 id 都能在 `frontend/public/ontology/metadata.json` 里找到(链接完整性)。
- schema 校验:`ontology_id` 为可选;现有 registry 加载测试仍通过。
- 跑完 `extend_ontology.py` 后,`build_ontology.py` 的现有测试 `test_ontology_build.py` 不受影响(它跑在 OWL 缺失时 skip)。

## Out of scope

- 不获取、不编辑、不重生成 SPACEO OWL 源。
- 不把这 5 个概念真正并入权威 SPACEO(那是协作者侧、后续事项;本扩展是 local stopgap 并已如此标注)。
- 不做其余 3 个"易懂性"子项(边界解释、buffer/raster 文案、进度步骤名)与暴露列 `value_col_meta`。
- Phase 2 前端 deep-link 呈现默认不做(待 review 决定)。

## Files touched (Phase 1)

- 新增 `backend/scripts/extend_ontology.py`
- 新增 `backend/tests/test_extend_ontology.py`
- 改 `frontend/public/ontology/{metadata.json, search-index.json, nodes/000093_2.json, nodes/000094_2.json, nodes/000292.json}` + 新增 `frontend/public/ontology/nodes/000295.json`(均由脚本生成,提交其产物)
- 改 `backend/app/data/variable_metadata.json`(9 个 `ontology_id`)
- 改 `backend/app/data/variable_metadata.schema.json`(可选 `ontology_id`)
- 改 `backend/app/routers/variables.py`(`VariableMetadataModel.ontology_id`)
- 改 `frontend/src/lib/api.ts`(`VariableMetadata.ontology_id?`)
- 改 `backend/tests/test_variable_registry.py`(链接完整性断言)
- 注释 `backend/scripts/build_ontology.py`(重建后需重跑 extend 的提醒)
