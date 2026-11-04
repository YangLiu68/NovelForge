`taiye-qiushen`, extractor `llm:openrouter:anthropic/claude-opus-5.5`: 51 claims, 58 labelled facts.

Precision **0.961** (strict, modality too: 0.941); recall **0.845** (asserted facts: 0.925); modality accuracy 0.98.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 11 | 10 | 10 |
| age | 11 | 9 | 9 |
| birthplace | 5 | 4 | 5 |
| eye_color | 9 | 9 | 9 |
| hair_color | 10 | 9 | 9 |
| handedness | 4 | 4 | 4 |
| status | 8 | 4 | 5 |

Wrong claims:
- 2 孙嬷嬷 status=dead (reported): 她是天擦黑时看不清路，失脚栽下去的
- 4 白昙 birthplace=于阗王城外 (asserted): 她的第一声啼哭，是落在于阗王城外的沙地上的

Modality errors:
- 4 李昀 ability:swim=learned: asserted, label recalled: 裴照每天黄昏都在那片浅湾里教他凫水

Missed facts:
- 1 许青禾 age=7 (recalled): 她七岁
- 1 许青禾 ability:read=cannot (reported): 听说你不识字
- 2 郑令仪 age=38 (asserted): 她今年三十有八
- 2 李昀 status=dead (reported): 小殿下没气了
- 2 孙嬷嬷 status=dead (reported): 孙嬷嬷没了
- 2 孙嬷嬷 status=dead (hedged): 把孙嬷嬷也克死了
- 4 白昙 birthplace=于阗 (asserted): 她的第一声啼哭，是落在于阗
- 4 郑令仪 hair_color=white (asserted): 她就散着一头白发
- 4 孙嬷嬷 status=dead (reported): 孙嬷嬷死了
