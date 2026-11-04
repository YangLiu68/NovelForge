`wugang-xinzha`, extractor `llm:openrouter:anthropic/claude-opus-5.5`: 35 claims, 31 labelled facts.

Precision **0.829** (strict, modality too: 0.829); recall **0.935** (asserted facts: 1.0); modality accuracy 1.0.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 5 | 5 | 5 |
| age | 7 | 7 | 7 |
| birthplace | 1 | 1 | 1 |
| eye_color | 5 | 5 | 5 |
| hair_color | 6 | 6 | 6 |
| handedness | 2 | 2 | 2 |
| location | 2 | 1 | 6 |
| status | 3 | 2 | 3 |

Wrong claims:
- 1 林雪棠 location=海关钟楼底下 (asserted): 林雪棠站在海关钟楼底下，把大衣领子竖了起来。
- 1 陈砚 location=码头账房 (asserted): 码头账房在三号仓库的二楼
- 1 林雪棠 location=渔村 (asserted): 林雪棠去了一趟渔村，找到了周铁山
- 1 周铁山 status=alive (asserted): 周铁山是海燕号上唯一活着回来的水手
- 2 陈砚 location=码头 (asserted): 陈砚在码头等她
- 2 苏婉 location=岸上 (asserted): 苏婉留在岸上

Missed facts:
- 1 周铁山 status=dead (hedged): 他年轻时在南洋跑过船，听说十几岁就死过一回
- 2 陈砚 location=雾港 (recalled): 陈砚生在临江县，十二岁跟着叔叔来到雾港
