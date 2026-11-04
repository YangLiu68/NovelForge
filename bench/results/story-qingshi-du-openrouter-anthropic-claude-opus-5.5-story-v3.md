*青石渡* (`qingshi-du`): 8 chapters, 9 characters. LLM `openrouter:anthropic/claude-opus-5.5`, prompts `story-v3`, 68 calls, 104,224 input / 41,211 output tokens, 656.7 s in the model.

Labelled problems found: **3 / 6** (5 flagged at the right place with any diagnosis); traps set off: **0 / 4**; issues reported: 21 (11 not on a label).

| Label | Kind | Result | Issues |
|---|---|---|---|
| H1 | character | found | I1 |
| H2 | character | other diagnosis (I3) |  |
| H3 | plot | found | I4, I5, I7 |
| H4 | plot | other diagnosis (I10, I14) |  |
| H5 | plot | missed |  |
| H6 | pacing | found | I15 |
| U1 | trap | clean (verdicts: consistent) |  |
| U2 | trap | clean (verdicts: delayed) |  |
| U3 | trap | clean |  |
| U4 | trap | clean (verdicts: consistent) |  |

| Issue | Severity | Kind | Chapter | Character | What |
|---|---|---|---|---|---|
| I1 | 3 | 与人设冲突 | 3 | 程歌 | 程歌拨开围观人群，当街打了段少钧一记耳光。 |
| I2 | 3 | 与人设冲突 | 3 | 程歌 | 程歌指着段少钧的鼻子，当众斥责他欺负青石镇百姓。 |
| I3 | 3 | 与人设冲突 | 4 | 赵启明 | 赵启明趁程歌不在，抽出她的卷子撕碎，扔进炭盆烧掉。 |
| I4 | 3 | 与人设冲突 | 5 | 程歌 | 程歌提着洗好的衣裳作掩护，从后门潜入督军府，径直走进祠堂。 |
| I5 | 3 | 与人设冲突 | 5 | 程歌 | 程歌从未进过祠堂，也没人告诉过她，却准确按下供桌前左边第三块砖，打开了暗格。 |
| I6 | 3 | 因果不通 | 4 | 程歌 | 暗格位置和打开方法只由段督军关起门私下告诉了孙账房，孙账房也答应保密；程歌从未进过祠堂、也没人告诉过她，却直接按对了左边第三块砖，她得知这个秘密的途径在前文中不存在。 |
| I7 | 3 | 信息来源不明 | 5 | 程歌 | 祠堂供桌前左边第三块砖下藏有暗格 |
| I8 | 2 | 为坏而坏 | 3 | 段少钧 | 段少钧踩住卖花姑娘捡花的手，笑着问她疼不疼。 |
| I9 | 2 | 与人设冲突 | 3 | 程歌 | 程歌扶起卖花姑娘，头也不回地离开了。 |
| I10 | 2 | 与人设冲突 | 7 | 许校长 | 许校长以会考作弊为由，把退学通知摆在程歌面前，要她退学。 |
| I11 | 2 | 与人设冲突 | 8 | 许校长 | 许校长告诉程歌，她父亲曾替自己交了三年学费，减她一半学费是在还这份情。 |
| I12 | 2 | 伏笔未回收 | 4 |  | 段督军把私账藏进祠堂供桌下的暗格，只告诉了孙账房，并叮嘱不许外传，这个秘密日后显然会泄露或被用上。 |
| I13 | 2 | 伏笔未回收 | 5 |  | 程歌从没进过祠堂，也没人告诉过她暗格的位置，却能准确打开，她如何得知成了未解之谜。 |
| I14 | 2 | 伏笔未回收 | 7 |  | 突然出现替程歌解围的神秘中年人身份不明，来意成谜。 |
| I15 | 2 | 节奏平 | 6 |  | 第 6 章紧张度只有 1，章末没有钩子 |
| I16 | 1 | 为坏而坏 | 3 | 段少钧 | 段少钧一脚踢翻了卖花姑娘的竹篮。 |
| I17 | 1 | 动机缺失 | 4 | 段督军 | 段督军关起书房门，把私账新的藏匿地点和打开方法告诉孙账房，并嘱咐不许外传。 |
| I18 | 1 | 章末无钩子 | 2 |  | 第 2 章章末没有钩子 |
| I19 | 1 | 章末无钩子 | 4 |  | 第 4 章章末没有钩子 |
| I20 | 1 | 章末无钩子 | 5 |  | 第 5 章章末没有钩子 |
| I21 | 1 | 章末无钩子 | 7 |  | 第 7 章章末没有钩子 |

Grounding: 53 notes, 36 beats, 6 setups kept; quotes located by {'exact': 89}; rejected {'plan: no known target or chapter out of range': 1}; verdicts changed by checks {'unmotivated -> delayed': 1, 'contradicts -> delayed': 2, 'consistent -> contradicts': 1}; errors 0.
