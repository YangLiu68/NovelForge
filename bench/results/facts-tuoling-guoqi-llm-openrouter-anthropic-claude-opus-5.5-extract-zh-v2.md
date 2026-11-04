`tuoling-guoqi`, extractor `llm:openrouter:anthropic/claude-opus-5.5`: 49 claims, 56 labelled facts.

Precision **0.98** (strict, modality too: 0.98); recall **0.857** (asserted facts: 0.952); modality accuracy 1.0.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 11 | 9 | 10 |
| age | 12 | 9 | 9 |
| birthplace | 5 | 5 | 5 |
| eye_color | 8 | 8 | 8 |
| hair_color | 11 | 10 | 10 |
| handedness | 4 | 4 | 4 |
| status | 5 | 3 | 3 |

Wrong claims:
- 2 尉迟兰 ability:ride=used (asserted): 尉迟兰已经能自己控着缰绳，绕着驼队歇脚的那片沙窝子小跑一圈了

Missed facts:
- 1 康米娜 age=7 (recalled): 康米娜生在碎叶，七岁那年
- 1 尉迟兰 age=10 (recalled): 尉迟兰生在于阗，十岁
- 2 尉迟兰 ability:ride=learned (asserted): 尉迟兰已经能自己控着缰绳
- 2 卫长庚 age=70 (reported): 老卫七十岁的人了
- 2 石小满 status=dead (hedged): 所有人都以为小满死了
- 2 石小满 status=alive (reported): 他还活着
- 4 尉迟兰 ability:ride=cannot (reported): 你连骆驼都爬不上去
- 4 康米娜 hair_color=red (asserted): 她站在驼队的最前头，红头发
