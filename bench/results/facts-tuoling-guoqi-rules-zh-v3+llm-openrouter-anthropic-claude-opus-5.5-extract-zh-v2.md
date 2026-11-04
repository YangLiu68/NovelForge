`tuoling-guoqi`, extractor `rules-zh-v3+llm:openrouter:anthropic/claude-opus-5.5`: 55 claims, 56 labelled facts.

Precision **0.927** (strict, modality too: 0.927); recall **0.911** (asserted facts: 0.952); modality accuracy 1.0.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 11 | 9 | 12 |
| age | 12 | 11 | 11 |
| birthplace | 5 | 5 | 5 |
| eye_color | 8 | 8 | 8 |
| hair_color | 11 | 10 | 11 |
| handedness | 4 | 4 | 4 |
| status | 5 | 4 | 4 |

Wrong claims:
- 1 尉迟兰 ability:ride=used (reported): 兰娘子骑马
- 2 裴照 hair_color=white (asserted): 裴照头一个跑过去，跪在白发
- 2 尉迟兰 ability:ride=used (asserted): 尉迟兰已经能自己控着缰绳，绕着驼队歇脚的那片沙窝子小跑一圈了
- 4 尉迟兰 ability:ride=used (asserted): 尉迟兰是骑马来的，骑

Missed facts:
- 2 尉迟兰 ability:ride=learned (asserted): 尉迟兰已经能自己控着缰绳
- 2 卫长庚 age=70 (reported): 老卫七十岁的人了
- 2 石小满 status=alive (reported): 他还活着
- 4 尉迟兰 ability:ride=cannot (reported): 你连骆驼都爬不上去
- 4 康米娜 hair_color=red (asserted): 她站在驼队的最前头，红头发
