`taiye-qiushen`, extractor `rules-zh-v3`: 36 claims, 58 labelled facts.

Precision **1.0** (strict, modality too: 0.944); recall **0.621** (asserted facts: 0.7); modality accuracy 0.944.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 11 | 4 | 4 |
| age | 11 | 9 | 9 |
| birthplace | 5 | 1 | 1 |
| eye_color | 9 | 8 | 8 |
| hair_color | 10 | 6 | 6 |
| handedness | 4 | 2 | 2 |
| status | 8 | 6 | 6 |

Modality errors:
- 1 李昀 age=4: asserted, label recalled: 他才四岁
- 2 孙嬷嬷 status=dead: asserted, label hedged: 孙嬷嬷也克死了

Missed facts:
- 1 许青禾 handedness=left (asserted): 她惯用左手
- 1 许青禾 birthplace=明州 (asserted): 许青禾今年十六，明州人
- 1 许青禾 age=7 (recalled): 她七岁
- 1 许青禾 ability:swim=learned (recalled): 她七岁就能跟着哥哥们凫水
- 1 许青禾 ability:read=cannot (asserted): 她一个字也不认得
- 1 许青禾 ability:read=cannot (reported): 听说你不识字
- 1 白昙 ability:read=cannot (reported): 我认不得
- 1 裴照 birthplace=凉州 (hedged): 有人说他生在凉州
- 2 郑令仪 age=38 (asserted): 她今年三十有八
- 2 许青禾 ability:swim=used (asserted): 她蹬开荷梗，游到那只手边上
- 2 李昀 status=dead (reported): 小殿下没气了
- 2 白昙 hair_color=auburn (asserted): 白昙赤褐色的长辫
- 2 白昙 eye_color=green (asserted): 她没有哭，一双绿眼睛
- 2 孙嬷嬷 status=dead (reported): 孙嬷嬷没了
- 3 许青禾 ability:read=used (asserted): 她把那张纸凑到窗下，一行一行地读下去
- 3 裴照 birthplace=沙州 (reported): 我生在沙州
- 4 李昀 ability:swim=learned (recalled): 教他凫水
- 4 李昀 handedness=right (asserted): 他自幼惯使右手
- 4 白昙 hair_color=auburn (asserted): 她重新编起了辫子，赤褐色的
- 4 白昙 birthplace=于阗 (asserted): 她的第一声啼哭，是落在于阗
- 4 郑令仪 hair_color=white (asserted): 郑氏的头发原来早就白了
- 4 郑令仪 hair_color=black (recalled): 替她细细染一遍，染得比墨还黑
