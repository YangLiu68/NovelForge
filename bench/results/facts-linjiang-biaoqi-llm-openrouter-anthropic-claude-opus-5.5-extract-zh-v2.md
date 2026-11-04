`linjiang-biaoqi`, extractor `llm:openrouter:anthropic/claude-opus-5.5`: 43 claims, 52 labelled facts.

Precision **0.953** (strict, modality too: 0.93); recall **0.788** (asserted facts: 0.811); modality accuracy 0.976.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 19 | 13 | 13 |
| age | 9 | 7 | 7 |
| birthplace | 5 | 4 | 5 |
| eye_color | 5 | 5 | 5 |
| hair_color | 4 | 4 | 4 |
| handedness | 5 | 5 | 5 |
| status | 5 | 3 | 4 |

Wrong claims:
- 1 林照雪 status=dead (recalled): 照雪十岁那年，娘得痨病撒手去了
- 1 苏砚 birthplace=云州城外的一个小渡口 (asserted): 苏砚生在云州城外的一个小渡口

Modality errors:
- 3 楚青萝 hair_color=brown: recalled, label asserted: 青萝的头发还是褐色的

Missed facts:
- 1 林照雪 age=10 (recalled): 照雪十岁那年
- 1 苏砚 birthplace=云州 (asserted): 苏砚生在云州
- 1 林守拙 ability:read=used (asserted): 林守拙展开文书，凑在灯下看了许久
- 1 楚青萝 age=7 (recalled): 她生在疏勒，七岁那年
- 1 林照雪 ability:ride=cannot (reported): 你连马都不会骑
- 2 楚青萝 ability:ride=used (asserted): 楚青萝骑着一匹枣红马
- 2 韩七 ability:ride=used (asserted): 他骑在一匹通身乌黑的高头大马上
- 3 林守拙 status=alive (recalled): 林守拙差点没熬过那个冬天
- 3 林照雪 ability:ride=used (asserted): 如今她骑着那匹白蹄乌
- 4 韩七 ability:read=used (asserted): 韩七把那封信抖开，借着火把的光一行一行看下去
- 4 周铁山 status=alive (asserted): 周镖头蹲在门槛上抽旱烟
