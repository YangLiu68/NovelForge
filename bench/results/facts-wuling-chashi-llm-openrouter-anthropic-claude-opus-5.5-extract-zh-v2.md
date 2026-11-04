`wuling-chashi`, extractor `llm:openrouter:anthropic/claude-opus-5.5`: 47 claims, 61 labelled facts.

Precision **1.0** (strict, modality too: 1.0); recall **0.77** (asserted facts: 0.875); modality accuracy 1.0.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 19 | 11 | 11 |
| age | 12 | 10 | 10 |
| birthplace | 4 | 4 | 4 |
| eye_color | 6 | 6 | 6 |
| hair_color | 12 | 10 | 10 |
| handedness | 2 | 2 | 2 |
| status | 6 | 4 | 4 |

Missed facts:
- 1 叶芙 ability:ride=cannot (reported): 叶芙往后退了半步：“我不会骑马
- 1 岩温 ability:swim=cannot (reported): 他说，“我不会水
- 1 苏怀山 age=16 (recalled): 他十六岁那年
- 2 叶芙 ability:ride=used (asserted): 叶芙骑着白马
- 2 苏怀山 status=alive (reported): 趁我还活着
- 2 何景行 ability:read=used (asserted): 何景行没再多问，拆开随身带来的牛皮纸袋，抽出几页纸，清了清嗓子，一条一条地念下去
- 3 何景行 ability:read=used (reported): 何律师亲口念的
- 3 苏晚棠 ability:read=used (asserted): 苏晚棠没吭声，把合同拿过去，一页一页翻着看
- 3 苏晚棠 age=3 (recalled): 苏晚棠生在大理，三岁那年
- 3 何景行 status=dead (hedged): 都以为何景行已经死
- 3 叶芙 ability:ride=used (asserted): 她是伏在马背上
- 3 叶芙 hair_color=black (hedged): 叶芙的头发看上去几乎是黑的
- 3 苏明澈 hair_color=silver (asserted): 苏明澈站在门口，那头银白的头发
- 4 苏明澈 ability:read=used (asserted): 苏明澈翻了翻本子，报了个数
