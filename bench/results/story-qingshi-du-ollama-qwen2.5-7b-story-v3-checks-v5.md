*青石渡* (`qingshi-du`): 8 chapters, 9 characters. LLM `replay:ollama:qwen2.5:7b`, prompts `story-v3`, checks `checks-v5`, 50 calls, 32,349 input / 8,069 output tokens, 996.8 s in the model.

Labelled problems found: **3 / 6** (3 flagged at the right place with any diagnosis); traps set off: **1 / 4**; issues reported: 8 (4 not on a label).

| Label | Kind | Result | Issues |
|---|---|---|---|
| H1 | character | missed |  |
| H2 | character | found | I1 |
| H3 | plot | found | I2 |
| H4 | plot | missed |  |
| H5 | plot | missed |  |
| H6 | pacing | found | I6 |
| U1 | trap | set off (verdicts: malice_without_cause) | I8 |
| U2 | trap | clean (verdicts: routine) |  |
| U3 | trap | clean |  |
| U4 | trap | clean |  |

| Issue | Severity | Kind | Chapter | Character | What |
|---|---|---|---|---|---|
| I1 | 3 | 为坏而坏 | 4 | 赵启明 | 撕碎程歌的作文卷子 |
| I2 | 3 | 与人设冲突 | 5 | 程歌 | 进入督军府祠堂并发现暗格 |
| I3 | 3 | 因果不通 | 8 |  | 程歌在第8章才得知蓝皮账册的存在，但在此之前已经将账册的头几页抄了一份并送给了孙账房。 |
| I4 | 2 | 为坏而坏 | 8 | 程歌 | 与舅母对话，舅母冷嘲热讽。 |
| I5 | 2 | 伏笔未回收 | 4 |  | 督军挪动了私账藏匿地点给孙账房交代 |
| I6 | 2 | 节奏平 | 6 |  | 第 6–8 章紧张度只有 1、2、1 |
| I7 | 1 | 与人设冲突 | 1 | 程歌 | 藏起父亲留下的信 |
| I8 | 1 | 为坏而坏 | 1 | 周舅母 | 拍账本责备程歌的学费问题 |

Grounding: 30 notes, 24 beats, 2 setups kept; quotes located by {'exact': 51, 'piece': 1, 'sentence': 2}; rejected {'shape: setup quote not found': 5, 'notes: quote not found in the chapter': 1, 'beats: quote not found in the chapter': 1}; verdicts changed by checks {'routine -> delayed': 1, 'routine -> contradicts': 2, 'contradicts -> malice_without_cause': 1, 'consistent -> unverified': 2, 'routine -> consistent': 1}; errors 2.
