`tuoling-guoqi`, extractor `llm:openrouter:anthropic/claude-haiku-5.5`: 47 claims, 56 labelled facts.

Precision **0.979** (strict, modality too: 0.957); recall **0.821** (asserted facts: 0.905); modality accuracy 0.978.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 11 | 8 | 9 |
| age | 12 | 9 | 9 |
| birthplace | 5 | 5 | 5 |
| eye_color | 8 | 8 | 8 |
| hair_color | 11 | 9 | 9 |
| handedness | 4 | 4 | 4 |
| status | 5 | 3 | 3 |

Wrong claims:
- 2 尉迟兰 ability:ride=used (asserted): 尉迟兰已经能自己控着缰绳，绕着驼队歇脚的那片沙窝子小跑一圈了

Modality errors:
- 3 康米娜 hair_color=black: recalled, label reported: 你这头黑发

Missed facts:
- 1 康米娜 age=7 (recalled): 康米娜生在碎叶，七岁那年
- 1 尉迟兰 age=10 (recalled): 尉迟兰生在于阗，十岁
- 1 裴照 ability:ride=used (asserted): 裴照翻身上了马
- 2 尉迟兰 ability:ride=learned (asserted): 尉迟兰已经能自己控着缰绳
- 2 卫长庚 age=70 (reported): 老卫七十岁的人了
- 2 石小满 status=dead (hedged): 所有人都以为小满死了
- 2 石小满 status=alive (reported): 他还活着
- 2 安鹤年 hair_color=white (asserted): 白发苍苍的安鹤年
- 4 尉迟兰 ability:ride=cannot (reported): 你连骆驼都爬不上去
- 4 康米娜 hair_color=red (asserted): 她站在驼队的最前头，红头发
