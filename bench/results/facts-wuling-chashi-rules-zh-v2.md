`wuling-chashi`, extractor `rules-zh-v2`: 38 claims, 61 labelled facts.

Precision **0.947** (strict, modality too: 0.868); recall **0.59** (asserted facts: 0.625); modality accuracy 0.917.

| Predicate | Facts | Found | Claims |
|---|---|---|---|
| ability | 19 | 6 | 6 |
| age | 12 | 10 | 11 |
| birthplace | 4 | 2 | 2 |
| eye_color | 6 | 6 | 6 |
| hair_color | 12 | 8 | 9 |
| handedness | 2 | 1 | 1 |
| status | 6 | 3 | 3 |

Wrong claims:
- 1 苏怀山 age=36 (asserted): 苏怀山上了雾岭，今年三十六岁
- 3 叶芙 hair_color=red (asserted): 叶芙骑上那匹白马冲进了雨里，栗红色的头发

Modality errors:
- 3 苏明澈 hair_color=black: asserted, label recalled: 苏明澈把一头黑发
- 3 何景行 eye_color=blue: hedged, label asserted: 何景行那双蓝眼睛
- 4 苏明澈 hair_color=silver: asserted, label recalled: 他那头银发

Missed facts:
- 1 何景行 hair_color=black (asserted): 他一头黑发
- 1 叶芙 hair_color=auburn (asserted): 她的眼睛是绿的，浅浅的一汪，像刚冒头的茶芽；头发是栗红色的
- 1 岩温 birthplace=景迈山 (asserted): 岩温是布朗族人，生在景迈山
- 1 岩温 age=36 (asserted): 岩温是布朗族人，生在景迈山，很早就跟着苏怀山上了雾岭，今年三十六岁
- 1 叶芙 ability:ride=cannot (reported): 叶芙往后退了半步：“我不会骑马
- 1 叶芙 ability:ride=cannot (asserted): 她确实不会
- 1 苏晚棠 ability:ride=used (asserted): 苏晚棠踩着马镫翻身上了白马
- 1 苏晚棠 ability:ride=learned (recalled): 她小时候每年暑假都在山上过，骑马是爷爷手把手教会的
- 1 何景行 ability:ride=used (asserted): 何景行犹豫了一下，把公文包挂到鞍子上，也上了马
- 1 岩温 ability:swim=cannot (reported): 他说，“我不会水
- 2 叶芙 ability:ride=used (asserted): 叶芙骑着白马
- 2 苏怀山 ability:read=used (asserted): 他从上衣口袋里摸出老花镜戴上，把信纸凑到窗前的亮处，一行一行地往下看
- 2 苏怀山 status=alive (reported): 趁我还活着
- 2 何景行 ability:read=used (asserted): 何景行没再多问，拆开随身带来的牛皮纸袋，抽出几页纸，清了清嗓子，一条一条地念下去
- 2 苏怀山 age=82 (asserted): 苏怀山咽了气，享年八十二岁
- 3 何景行 ability:read=used (reported): 何律师亲口念的
- 3 苏晚棠 ability:read=used (asserted): 苏晚棠没吭声，把合同拿过去，一页一页翻着看
- 3 何景行 status=dead (reported): 是何律师的车，”那人在电话里喊，“埋了大半截，人怕是没了
- 3 叶芙 hair_color=auburn (asserted): 叶芙骑上那匹白马冲进了雨里，栗红色的头发
- 3 叶芙 ability:ride=used (asserted): 她是伏在马背上
- 4 苏怀山 status=dead (asserted): 老爷子走了一年多了
- 4 苏明澈 hair_color=black (asserted): 他那头银发早剪了，如今又是一头黑发
- 4 岩温 handedness=right (asserted): 他是个右撇子
- 4 岩温 birthplace=勐海 (reported): 岩温哥是勐海人
- 4 苏明澈 ability:read=used (asserted): 苏明澈翻了翻本子，报了个数
