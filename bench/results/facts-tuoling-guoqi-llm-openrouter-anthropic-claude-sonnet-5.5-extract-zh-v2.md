`tuoling-guoqi`, extractor `llm:openrouter:anthropic/claude-sonnet-5.5`: 46 claims, 56 labelled facts.

Precision **0.978** (strict, modality too: 0.978); recall **0.804** (asserted facts: 0.905); modality accuracy 1.0.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 11 | 8 | 8 |
| age | 12 | 9 | 9 |
| birthplace | 5 | 4 | 4 |
| eye_color | 8 | 7 | 7 |
| hair_color | 11 | 10 | 10 |
| handedness | 4 | 4 | 4 |
| status | 5 | 3 | 4 |

Wrong claims:
- 1 康米娜 status=dead (asserted): 去年冬天，她父亲康拂延死在西州

Missed facts:
- 1 康米娜 age=7 (recalled): 康米娜生在碎叶，七岁那年
- 1 尉迟兰 age=10 (recalled): 尉迟兰生在于阗，十岁
- 2 尉迟兰 ability:ride=learned (asserted): 尉迟兰已经能自己控着缰绳
- 2 卫长庚 age=70 (reported): 老卫七十岁的人了
- 2 尉迟兰 eye_color=black (hedged): 尉迟兰的眼睛看上去几乎是黑的
- 2 石小满 status=dead (hedged): 所有人都以为小满死了
- 2 石小满 status=alive (asserted): 小满还活着
- 3 尉迟兰 birthplace=龟兹 (reported): 她是龟兹生人
- 4 尉迟兰 ability:ride=cannot (reported): 你连骆驼都爬不上去
- 4 卫长庚 ability:read=used (asserted): 老卫眯起眼睛，就着日头，一行一行地念了下去
- 4 康米娜 hair_color=red (asserted): 她站在驼队的最前头，红头发
