*雪夜当铺* (`xueye-dangpu`): 8 chapters, 12 characters. LLM `replay:ollama:qwen2.5:7b`, prompts `story-v3`, 57 calls, 41,097 input / 10,544 output tokens, 1370.2 s in the model.

Labelled problems found: **5 / 6** (5 flagged at the right place with any diagnosis); traps set off: **1 / 8**; issues reported: 7 (1 not on a label).

| Label | Kind | Result | Issues |
|---|---|---|---|
| P1 | character | found | I1 |
| P2 | character | found | I6 |
| P3 | plot | missed |  |
| P4 | plot | found | I3 |
| P5 | plot | found | I4 |
| P6 | pacing | found | I5 |
| T1 | trap | set off (verdicts: contradicts) | I2 |
| T2 | trap | clean |  |
| T3 | trap | clean |  |
| T4 | trap | clean |  |
| T5 | trap | clean (verdicts: consistent, consistent) |  |
| T6 | trap | clean |  |
| T7 | trap | clean |  |
| T8 | trap | clean |  |

| Issue | Severity | Kind | Chapter | Character | What |
|---|---|---|---|---|---|
| I1 | 3 | 与人设冲突 | 2 | 沈知微 | 给了小乞丐二十文钱 |
| I2 | 3 | 与人设冲突 | 4 | 沈知微 | 请小六吃了一碗腊八粥并给他五十文钱。 |
| I3 | 3 | 天降解围 | 7 |  | 钦差大人突然出现并解救主角，显得突兀。 |
| I4 | 2 | 伏笔未回收 | 1 |  | 母亲临终前亲手给她系上的那块玉佩 |
| I5 | 2 | 节奏平 | 5 |  | 第 5–6 章紧张度只有 2、1，章末没有钩子 |
| I6 | 1 | 为坏而坏 | 3 | 沈若兰 | 推沈知微进冰窟窿 |
| I7 | 1 | 为坏而坏 | 8 | 沈知微 | 要求陈伯送客 |

Grounding: 40 notes, 28 beats, 2 setups kept; quotes located by {'exact': 56, 'normalized': 4, 'sentence': 6, 'piece': 2}; rejected {'shape: setup quote not found': 9, 'notes: quote not found in the chapter': 8, 'beats: quote not found in the chapter': 1, 'plot: causality without a cause and an effect': 2}; verdicts changed by checks {'consistent -> unverified': 3, 'routine -> contradicts': 2, 'consistent -> malice_without_cause': 1}; errors 0.
