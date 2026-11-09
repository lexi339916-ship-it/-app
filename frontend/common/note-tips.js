/**
 * 小知 · 记录内容点评
 *
 * 原则：每条提示必须先引用/提取用户记录里的真实内容，再按内容类型给评价；
 * 未命中主题时只基于当前记录提示补充信息，不套用与内容无关的通用夸奖。
 * 这里使用确定性规则，不调用外部模型，避免生成与输入不符的点评。
 */

export function noteTopic(note, max = 24) {
  const title = String((note && note.title) || '').trim()
  const content = String((note && note.content) || '').trim()
  let topic = title || content
  topic = topic.replace(/\s+/g, ' ')
  return topic.length > max ? `${topic.slice(0, max)}…` : topic
}

function whenHint(text) {
  if (/下午/.test(text)) return '下午'
  if (/上午|早上/.test(text)) return '早上'
  if (/晚上|今晚/.test(text)) return '晚上'
  if (/明天/.test(text)) return '明天'
  if (/周末/.test(text)) return '周末'
  return '到时间'
}

function foodPrep(text) {
  if (/拌面|面条|面/.test(text)) return '面条和配菜'
  if (/早餐|吐司/.test(text)) return '吐司、鸡蛋和喜欢的配料'
  if (/咖啡/.test(text)) return '咖啡豆和水'
  if (/火锅/.test(text)) return '锅底和涮菜'
  if (/烘焙|甜点|蛋糕/.test(text)) return '面粉和模具'
  if (/饭|菜|做饭/.test(text)) return '食材和调味'
  return '要用的食材'
}

function ideaTip(note) {
  const topic = noteTopic(note)
  const text = `${note.title || ''} ${note.content || ''}`

  if (/咖啡/.test(text) && /写|周报|工作|看书|阅读/.test(text)) {
    return `“${topic}”这个场景很适合坐下来写点东西，先把要写的重点列成三条~`
  }
  if (/拌面|面条|早餐|咖啡|吐司|火锅|做饭|美食|烘焙|甜点|饭|菜/.test(text)) {
    return `“${topic}”这个想法很具体，先把${foodPrep(text)}准备好，${whenHint(text)}就能动手~`
  }
  if (/读书|阅读|书店|书|文章|诗/.test(text)) {
    return `“${topic}”很有画面感，可以顺手记下店名、书名或一句触动你的话，之后更容易回想~`
  }
  if (/周报|工作|项目|会议|同事|老板|汇报/.test(text)) {
    return `“${topic}”这个表达很清晰，可以按“问题—解决—下一步”先列三段~`
  }
  if (/学习|考试|课程|论文|复习|作业/.test(text)) {
    return `“${topic}”可以先拆成今天能完成的一小步，比如先列提纲或做完一页~`
  }
  if (/跑鞋|运动|跑步|健身|游泳|骑行/.test(text)) {
    return `“${topic}”先定一个轻量目标，比如热身十分钟，别一上来太猛~`
  }
  if (/买|采购|购物|预算|存钱|理财|下单/.test(text)) {
    return `“${topic}”先记下来，等确认预算和真实需要后再决定，避免冲动消费~`
  }
  if (/旅行|旅游|公园|散步|拍照|照片|展览/.test(text)) {
    return `“${topic}”这种生活片段值得留一张照片，也可以顺手记下当时的地点~`
  }
  if (/收拾|整理|打扫|阳台|收纳|绿植|家里/.test(text)) {
    return `“${topic}”这种改善小空间的念头很治愈，可以先量一下尺寸或列一份清单~`
  }
  if (/代码|编程|产品|设计|工具|App|功能/.test(text)) {
    return `“${topic}”可以先把最小可用的版本写下来，再决定先做哪一块~`
  }
  if (/朋友|家人|妈妈|爸爸|孩子|同学|礼物|生日/.test(text)) {
    return `“${topic}”里的人和事很重要，可以先想好一句最想说的话或准备一件小礼物~`
  }
  if (/早睡|睡觉|休息|作息/.test(text)) {
    return `“${topic}”可以先从今晚提前半小时放下手机开始，别一下子要求太多~`
  }
  if (text.trim()) {
    return `“${topic}”是你刚记下的内容；再补一句“想怎么做/什么时候做”，小知就能帮你把下一步说清楚~`
  }
  return '这条记录还没有正文，先写下一个小想法，小知就能针对内容给你建议~'
}

function moodTip(note) {
  const topic = noteTopic(note)
  const text = `${note.title || ''} ${note.content || ''}`

  if (/难过|低落|失望|伤心|委屈|孤独|想哭|崩溃|难受/.test(text)) {
    return `“${topic}”这种感受不好受，先允许自己难过一会儿；如果愿意，可以找信任的人说说话~`
  }
  if (/累|忙|压力|焦虑|烦|困|疲惫|加班|赶|撑/.test(text)) {
    return `“${topic}”听起来确实有点累，先照顾好自己的节奏，慢一点也没关系~`
  }
  if (/暖|小纸条|善意|被照顾|感动/.test(text)) {
    return `“${topic}”这种被善意击中的瞬间很珍贵，记得把这份温暖也留给自己~`
  }
  if (/晚霞|天空|天气|雨|风|阳光|月亮|星星|云/.test(text)) {
    return `“${topic}”里的景色很有画面感，愿这一刻的好心情多停留一会儿~`
  }
  if (/开心|高兴|快乐|很好|美好|喜欢|幸福|轻松|满足|惊喜|期待|治愈|不错/.test(text)) {
    return `“${topic}”里的好心情值得留住，愿这份轻松多停留一会儿~`
  }
  if (/踏实|平静|安静|安心|从容|松弛/.test(text)) {
    return `“${topic}”里有种安稳的力量，今天有好好照顾自己~`
  }
  if (/吃|饭|咖啡|奶茶|甜点|面/.test(text)) {
    return `“${topic}”这种小小的满足很治愈，慢慢享用就好~`
  }
  if (/同事|朋友|家人|妈妈|爸爸|孩子|同学|老板/.test(text)) {
    return `“${topic}”里的人和事对你很重要，记得也给自己留一点空间~`
  }
  return `“${topic}”这一刻被你认真记下来了；如果愿意，可以再补一句当时发生了什么~`
}

function todoTip(note) {
  const topic = noteTopic(note)
  const text = `${note.title || ''} ${note.content || ''} ${note.location || ''}`

  if (/喝水|水杯|饮水/.test(text)) {
    return `“${topic}”别忘了给自己准备水杯，喝水有益健康~`
  }
  if (/快递|取件|包裹/.test(text)) {
    return `“${topic}”记得带手机和取件码，别白跑一趟~`
  }
  if (/房租|交租|转账/.test(text)) {
    return `“${topic}”先确认金额和收款人，留好凭证~`
  }
  if (/跑鞋|运动|跑步|健身|游泳|骑行/.test(text)) {
    return `“${topic}”先热身，量力而行，别把自己累着~`
  }
  if (/会员|订阅|续费/.test(text)) {
    return `“${topic}”先看看最近的使用记录，再决定是否续费~`
  }
  if (/报告|PPT|答辩|作业|学习|复习/.test(text)) {
    return `“${topic}”先完成最重要的一步，剩下的会顺起来~`
  }
  if (/买|采购|购物|下单/.test(text)) {
    return `“${topic}”先看看预算和真实需要，再决定是否现在买~`
  }
  if (/药|医院|复诊|体检/.test(text)) {
    return `“${topic}”别忘了按时处理，身体的事优先~`
  }
  if (/电话|联系|回复|消息/.test(text)) {
    return `“${topic}”记得及时回复，别让事情一直挂着~`
  }
  return `“${topic}”这件事，先补上截止时间或下一步动作，会更容易执行~`
}

export function buildEntryTip(note, entryType) {
  if (entryType === 'mood') return moodTip(note || {})
  return ideaTip(note || {})
}

export function buildTodoTip(note) {
  return todoTip(note || {})
}
