# ruff: noqa: E501  (prompt prose; Chinese has no spaces to wrap at)
"""Prompts for the story-logic stages, in Chinese and English (picked by the novel's language).

Each stage asks for one small, checkable thing; the code, not the model, decides what counts:
quotes are located in the text, cited note and beat IDs must exist and come from the right
chapters, and verdicts that cite nothing are downgraded (see `audit.py`).
"""

from __future__ import annotations

PROMPT_VERSION = "story-v3"
# The deterministic checks applied to the model's answers (audit.py). A change here re-scores
# recorded runs without calling the model; stored audits are reused only for the same pair.
CHECKS_VERSION = "checks-v4"
AUDIT_VERSION = f"{PROMPT_VERSION}/{CHECKS_VERSION}"

NOTES = {
    "zh": """你是一名严谨的小说编辑，正在为一部中文小说整理人物档案。只根据给出的这一章正文，记录本章交代的、关于名单中人物的事实。kind 只能是：
- background：身世、经历（包括前世经历）
- personality：性格、处事原则
- goal：想要什么、打算做什么
- wound：创伤、恐惧、心结、仇怨
- situation：眼下的处境：钱财、地位、健康、受谁控制
- relationship：和别人的关系、恩情、债务、利益往来
- knowledge：人物掌握的关键信息，并写明来源（亲眼所见、亲耳听到、别人告诉、前世记忆）
每条 text 写成一句简短的话；quote 是支持这条事实的原文：从正文逐字照抄一句话（10 到 60 个字），不要把几句拼在一起，也不要改字。character 必须是名单里的正式名字。只记录正文写明或强烈暗示的内容，不推测、不评价。性格和原则只记录正文直接写出的，不要从本章的某个行为倒推（比如不能因为她给了钱，就记“心地善良”）。最多 12 条，没有就返回空列表。""",
    "en": """You are a careful fiction editor building character files for a novel. From this one
chapter only, record what the text establishes about the listed characters. kind is one of:
- background: family, history (including a past life)
- personality: temperament, principles, how they make decisions
- goal: what they want or plan
- wound: trauma, fear, grudge
- situation: money, status, health, who controls them right now
- relationship: ties, debts, favours, grudges with someone else
- knowledge: a key piece of information they hold, and its source (saw it, heard it, was told,
  remembers it from a past life)
Write each text as one short sentence. quote is the sentence that supports it, copied character
for character from the chapter (5 to 40 words; one sentence, not several stitched together).
character must be a listed name. Record only what the text states or strongly implies; do not
guess or judge. Record personality and principles only where the text states them, never by
reading them off an action in this chapter (not "generous" because she gave money away). At
most 12 notes; return an empty list if there are none.""",
}

BEATS = {
    "zh": """你是一名小说编辑。阅读这一章，按发生顺序找出推动情节或暴露人物性格的关键行为，最多 6 个：重要的选择、帮助或伤害别人、说出关键的话、动用某个秘密或资源、危机被解决的方式。一个行为只写一件事，不要把几件事合在一起。每个行为写明：
- character：行为人（名单中的名字；名单外的人物写原文里的称呼）
- action：做了什么，一句话，忠实于原文（拒绝就是拒绝，不要写反）
- quote：原文依据，逐字照抄一句话，10 到 60 个字，不要把几句拼在一起
- hostile：是否针对、伤害或算计别人
- target：针对谁（没有就写空字符串）
- cost：这件事让行为人付出了什么（钱、风险、得罪人），没有就写空字符串（不要写“无”）
- resolves_crisis：这个行为是否化解了某个人物正面临的危机或绝境（救人、解围、替人还债、当堂翻案）
- uses_secret：行为人是否用到了一条不是人人都知道的信息（暗语、密码、藏东西的地方、别人的计划、将来才发生的事）
- secret：用到的是什么信息，一句话；没有就写空字符串""",
    "en": """You are a fiction editor. Read this chapter and list, in order, the key beats that move
the plot or reveal character, at most 6: important choices, helping or harming someone, a line
that matters, using a secret or a resource, how a crisis gets resolved. One beat is one action;
do not merge several. For each:
- character: who acts (a listed name; for an unlisted person, how the text refers to them)
- action: what they do, one sentence, true to the text (a refusal is a refusal)
- quote: the supporting sentence copied character for character, 5 to 40 words, one sentence
- hostile: does it target, harm or scheme against someone
- target: whom (empty string if no one)
- cost: what it costs the actor (money, risk, making an enemy), empty string if nothing
- resolves_crisis: does it get someone out of a danger or a dead end (a rescue, paying a debt
  for them, overturning a verdict)
- uses_secret: does the actor use information not everyone has (a password, a hiding place,
  someone's plan, something that will only happen later)
- secret: that information in one sentence, or empty""",
}

SHAPE = {
    "zh": """你是一名擅长网文节奏的编辑。读这一章，回答：
- summary：本章一句话梗概
- tension：本章紧张程度，1 到 5（1 是日常、完全没有冲突；2 是小摩擦；3 是有明确的矛盾；4 是危机；5 是生死关头）
- emotions：读者在本章会有的感受，可多选：thrill（爽）、heartache（虐、心痛）、suspense（悬念）、tension（紧张）、warmth（温情）、anger（愤怒）、calm（平淡）
- hook：章末有没有让读者想立刻看下一章的钩子（悬念、危机、反转）；present 为 true 时 quote 抄本章最后一两句原文，否则 quote 写空字符串。平铺直叙、日常收尾的章末不算钩子
- setups：作者刻意埋下、明显要在后文兑现的伏笔，只有这几种：临终遗言或嘱托、信物、承诺或约定、没解开的谜团、预言。已经发生完的事、人物背景、债务、一般情节都不算伏笔。每个写明 key（伏笔的核心物件或人，2 到 6 个字，必须是原文里的词，比如“玉佩”）、text（一句话）、quote（原文一句）。没有就返回空列表""",
    "en": """You are an editor with a feel for pacing. Read this chapter and answer:
- summary: the chapter in one sentence
- tension: 1 to 5 (1 everyday, no conflict at all; 2 minor friction; 3 a clear conflict; 4 a
  crisis; 5 life or death)
- emotions: what readers feel, any of: thrill, heartache, suspense, tension, warmth, anger, calm
- hook: does the chapter end on something that makes readers turn the page (a question, a
  threat, a reversal); when present is true, quote the chapter's last sentence or two,
  otherwise quote is empty. A quiet, everyday ending is not a hook
- setups: only things the author plants on purpose to pay off later: last words or a dying
  request, a token, a promise, an unsolved mystery, a prophecy. Events that are over,
  background, debts and ordinary plot are not setups. Each with key (the object or person at its
  core, 1 to 3 words that occur in the text, e.g. "the pendant"), text (one sentence) and quote
  (one sentence of the text). An empty list if there are none""",
}

LEAK = {
    "zh": """你是一名检查故事线逻辑的编辑。下面这个行为里，行为人用到了一条信息。给出的是他到这一章为止的人物档案（编号 N），以及本章在这个行为之前的原文。他是怎么知道这条信息的？
- how：saw（亲眼看见）、heard（亲耳听到）、told（别人告诉他）、past_life（前世记忆）、none（前文没有交代）。只有他本人在场或被告知才算；别人私下说的、他不在场的对话不算。
- source：一句话说明来源；没有就写空字符串。
- source_notes：交代来源的档案编号；没有就返回空列表。
- source_quote：如果来源在本章此前的原文里，逐字抄那一句；否则写空字符串。""",
    "en": """You check a novel's plot logic. In the beat below the actor uses a piece of information.
Given are their file up to this chapter (IDs N...) and this chapter's text before the beat. How do
they know it?
- how: saw, heard, told, past_life, or none (the text never says). Only counts if they were
  there or were told; a private conversation they did not witness does not count.
- source: the source in one sentence, or empty.
- source_notes: the note IDs that establish the source; an empty list if none.
- source_quote: if the source is in this chapter's earlier text, that sentence copied exactly;
  otherwise empty.""",
}

MOTIVES = {
    "zh": """你是一名重视人物逻辑的小说编辑。下面是一个关键行为（编号 B），以及行为人到这一章为止的人物档案（编号 N；标“设定”的是作者写的人设）。逐项回答，不要下总结论：
- is_choice：这是不是一个需要理由的选择？会让行为人付出代价、冒风险、伤害或帮助别人、不合常理的，填 true；日常动作、顺理成章的反应，填 false。
- reason：前文交代过的、促使他这么做的理由，一句话。只有这些算理由：利益（钱、地位、婚事、前途）、恩情或仇怨、交易或算计、过去的经历或创伤、明确的目标。“看不顺眼”“天性坏”“就是想”“觉得有意思”都不算理由。前文找不到，就写空字符串，不要替作者编。
- reason_notes：给出这个理由的档案编号；没有就返回空列表。
- against：这个行为和他的人设、原则或处境（钱够不够、身份允不允许、有没有更好的选择）有没有冲突？有就写一句，没有写空字符串。
- against_notes：冲突的档案编号；没有就返回空列表。
- explanation：一两句话说明你的判断。
- severity：如果缺少理由或和人设冲突，读者会多出戏：1 轻微，2 明显，3 严重。
- fixes：如果缺少理由或有冲突，给 1 到 3 条具体修改建议（在前文补一段经历或利益冲突做铺垫；改写成符合人设的做法；让这个行为付出代价，并在后文得到回报）；否则返回空列表。
只能引用给出的编号。""",
    "en": """You are a fiction editor who cares about character logic. Below is one key beat (ID
B...) and the actor's file up to this chapter (IDs N...; "sheet" marks the author's own character
design). Answer each question; do not give an overall verdict:
- is_choice: is this a choice that needs a reason? true if it costs the actor something, takes a
  risk, harms or helps someone, or is out of the ordinary; false for routine actions and natural
  reactions.
- reason: the reason the earlier text gives for it, in one sentence. Only these count: interest
  (money, status, a marriage, prospects), a debt of gratitude or a grudge, a deal or a calculation,
  a past experience or wound, an explicit goal. "Dislikes her", "is just bad", "wanted to", "found
  it amusing" are not reasons. If the text gives none, leave it empty; do not invent one.
- reason_notes: the note IDs that give that reason; an empty list if none.
- against: does the beat go against the character's design, principles or situation (can they
  afford it, does their position allow it, did they have a better option)? One sentence, or empty.
- against_notes: the note IDs it goes against; an empty list if none.
- explanation: one or two sentences.
- severity: if the reason is missing or it goes against the character, how much it breaks the
  reader's belief: 1 minor, 2 clear, 3 serious.
- fixes: if the reason is missing or it goes against the character, 1 to 3 concrete fixes (plant
  an earlier experience or conflict of interest; rewrite the action to fit the character; give it
  a cost and a later payoff); otherwise an empty list.
Cite only the IDs given.""",
}

LATER = {
    "zh": """你是一名小说编辑。前文有一个行为被认为缺少动机。下面是这个行为，以及行为人在后面章节里的人物档案（编号 N）。后文有没有交代这个行为的真正原因（比如揭晓的恩情、隐藏的交易、过去的经历）？有的话 explained_by 填那一条的编号，why 用一句话说明；没有就都填空字符串。只能引用给出的编号。""",
    "en": """You are a fiction editor. An earlier beat was judged to lack a motive. Below is the
beat and the actor's notes from later chapters (IDs N...). Does a later chapter reveal the real
reason for it (a debt of gratitude, a hidden deal, a past experience)? If so, put that note's ID
in explained_by and say why in one sentence; otherwise leave both empty. Cite only given IDs.""",
}

PLOT = {
    "zh": """你是一名检查故事线逻辑的编辑。下面按章节顺序列出全书的关键行为（编号 B），以及人物掌握信息的记录（编号 N）。只找一类问题：
- causality：前后因果接不上：事情发生的条件不成立、时间顺序不可能、前后说法打架。只报原文里确实矛盾的地方，不要因为情节简略就报。
每个问题写明：kind（causality）、chapter（问题出现的章）、character（相关人物，没有就写空字符串）、refs（相关编号，至少两个行为编号：因和果）、explanation（一句话说明哪里接不上）、severity（1 到 3）、fixes（1 到 3 条修改建议）。没有问题就返回空列表，不要硬凑。""",
    "en": """You check a novel's plot logic. Below, in chapter order, are the key beats (IDs B...) and
records of what characters know (IDs N...). Find one kind of problem only:
- causality: cause and effect do not connect (a precondition is false, the order is
  impossible, two statements clash). Report only real contradictions in the text, not plot that
  is merely brief.
For each: kind (causality), chapter (where the problem is), character (or empty), refs (related
IDs, at least two beats: cause and effect), explanation (one sentence on what does not connect),
severity (1 to 3), fixes (1 to 3). Return an empty list if there are none; do not invent
problems.""",
}

RESCUE = {
    "zh": """你是一名小说编辑。下面这个行为化解了一场危机，而行为人在此前的章节里从未出场过。读者会不会觉得这是作者硬塞进来的救兵（天降解围），而不是人物自己的行动换来的结果？deus_ex_machina 填 true 或 false，why 用一句话说明；fixes 给 1 到 3 条修改建议（比如提前几章埋下这个人物或消息，或者改成主角自己布局、主动求援），不是天降解围就返回空列表。""",
    "en": """You are a fiction editor. The beat below gets someone out of a crisis, and the person
doing it has not appeared in any earlier chapter. Will readers feel the author dropped in a
rescuer (deus ex machina) rather than the characters earning the outcome? Answer
deus_ex_machina true or false and why in one sentence; fixes: 1 to 3 (set the person or the news
up chapters earlier, or let the protagonist plan it or ask for help), or an empty list.""",
}

PAYOFF = {
    "zh": """你是一名小说编辑。下面是前文埋下的一个伏笔（编号 S），以及它之后的关键行为（编号 B）。有没有哪个行为回应、兑现或揭开了这个伏笔？有的话 paid_off_by 填那个行为的编号，why 用一句话说明；没有就都填空字符串。只能引用给出的编号。""",
    "en": """You are a fiction editor. Below is a setup planted earlier (ID S...) and the key beats
after it (IDs B...). Does any beat answer, use or reveal that setup? If so, put that beat's ID in
paid_off_by and say how in one sentence; otherwise leave both empty. Cite only given IDs.""",
}

PLAN = {
    "zh": """你是一名擅长网文节奏的主编。下面是这部小说每章的梗概和紧张度，以及检查出的问题（编号 I）。给出 3 到 6 条修改方案：先解决严重的问题，同时让故事更跌宕起伏、更抓人。可用的手法（technique）：setup（补伏笔）、rewrite_motive（改写动机）、blessing_in_disguise（因祸得福：绝境里得到机遇）、reversal（反转）、past_life_memory（利用前世记忆）、golden_finger（金手指）、cliffhanger（章末悬念钩子）、cost_and_payoff（付出代价、后文回报）、cut（删改）、other。每条写明：targets（解决哪些问题的编号）、chapter（改在第几章）、technique、change（具体怎么改）、why（为什么这样改读者会更投入、更心痛或更爽）、sample（可选的一小段示范文字，不超过 120 字，不需要就写空字符串）。""",
    "en": """You are a senior editor with a feel for pacing. Below are each chapter's summary and
tension, and the problems found (IDs I...). Give 3 to 6 revisions: fix the serious problems
first, and make the story more gripping. Techniques: setup, rewrite_motive,
blessing_in_disguise (a setback that opens an opportunity), reversal, past_life_memory,
golden_finger (a special advantage that explains a fast rise), cliffhanger, cost_and_payoff,
cut, other. For each: targets (problem IDs), chapter, technique, change (exactly what to change),
why (why readers will care more), sample (an optional short passage, at most 80 words, or
empty).""",
}

LABELS = {
    "zh": {
        "cast": "人物名单",
        "aliases": "别称",
        "chapter": "第 {n} 章",
        "text": "正文",
        "beat": "行为",
        "quote": "原文",
        "cost": "代价",
        "target": "对象",
        "file": "人物档案",
        "sheet": "设定",
        "later_file": "后文档案",
        "beats": "关键行为",
        "setups": "伏笔",
        "knowledge": "人物掌握的信息",
        "summaries": "每章梗概",
        "issues": "检查出的问题",
        "tension": "紧张度",
        "hook": "章末钩子",
        "yes": "有",
        "no": "无",
        "secret": "用到的信息",
        "before": "本章此前的原文",
    },
    "en": {
        "cast": "Characters",
        "aliases": "also called",
        "chapter": "Chapter {n}",
        "text": "Text",
        "beat": "Beat",
        "quote": "quote",
        "cost": "cost",
        "target": "target",
        "file": "Character file",
        "sheet": "sheet",
        "later_file": "Later notes",
        "beats": "Key beats",
        "setups": "Setups",
        "knowledge": "What characters know",
        "summaries": "Chapter summaries",
        "issues": "Problems found",
        "tension": "tension",
        "hook": "ending hook",
        "yes": "yes",
        "no": "no",
        "secret": "information used",
        "before": "This chapter before the beat",
    },
}
