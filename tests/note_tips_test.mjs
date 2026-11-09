import assert from 'node:assert/strict'
import { buildEntryTip, buildTodoTip } from '../frontend/common/note-tips.js'

let passed = 0
function check(name, cond) {
  if (!cond) throw new Error(`FAIL: ${name}`)
  passed += 1
  console.log(`[PASS] ${name}`)
}

const noodle = buildEntryTip({ title: '今天下午做一份拌面' }, 'idea')
check('拌面点评引用原文并给备料建议',
  noodle.includes('拌面') && noodle.includes('面条和配菜') && noodle.includes('下午'))

const weekly = buildEntryTip({ title: '把周报写成一个故事' }, 'idea')
check('周报点评引用原文并给结构建议',
  weekly.includes('周报') && weekly.includes('问题—解决—下一步') && !weekly.includes('面条'))

const coffee = buildEntryTip(
  { title: '咖啡店的灵感', content: '靠窗的位置适合写周报' }, 'idea')
check('咖啡店写周报不会被误判成做饭',
  coffee.includes('咖啡店的灵感') && coffee.includes('重点列成三条') && !coffee.includes('面条'))

const book = buildEntryTip({ title: '旧书店的下午' }, 'idea')
check('旧书店点评引用原文并给记录建议',
  book.includes('旧书店') && book.includes('书名'))

const plant = buildEntryTip({ title: '给阳台添一盆绿植' }, 'idea')
check('绿植点评引用原文并给尺寸建议',
  plant.includes('阳台') && plant.includes('尺寸'))

const unknownIdea = buildEntryTip({ title: '突然想到一个点子' }, 'idea')
check('未知主题只基于原文提示补充下一步',
  unknownIdea.includes('突然想到一个点子') && /下一步|时间/.test(unknownIdea))

const tired = buildEntryTip({ title: '有点累，但还算踏实' }, 'mood')
check('疲惫心情引用原文并给休息建议',
  tired.includes('有点累') && tired.includes('累') && tired.includes('节奏'))

const warm = buildEntryTip({ title: '被同事的小纸条暖到' }, 'mood')
check('被暖到的心情引用原文并给正向回应',
  warm.includes('小纸条') && warm.includes('温暖'))

const sad = buildEntryTip({ title: '今天有点难过' }, 'mood')
check('难过心情引用原文并给温和回应',
  sad.includes('今天有点难过') && sad.includes('难过'))

const sunset = buildEntryTip({ title: '今天的晚霞像橘子汽水' }, 'mood')
check('晚霞心情引用原文而不是套用通用夸奖',
  sunset.includes('晚霞') && sunset.includes('好心情'))

const unknownMood = buildEntryTip({ title: '记一下此刻' }, 'mood')
check('未知心情只基于原文邀请补充',
  unknownMood.includes('记一下此刻') && unknownMood.includes('发生了什么'))

const drink = buildTodoTip({ title: '四点喝水', content: '提醒我四点的时候喝水' })
check('喝水待办引用原文并给水杯提醒',
  drink.includes('四点喝水') && drink.includes('水杯'))

const parcel = buildTodoTip({ title: '取快递', content: '下午去取件' })
check('取快递待办引用原文并取件码提醒',
  parcel.includes('取快递') && parcel.includes('取件码'))

const rent = buildTodoTip({ title: '交下个月房租 2500' })
check('房租待办引用原文并金额凭证提醒',
  rent.includes('交下个月房租 2500') && rent.includes('金额') && rent.includes('凭证'))

const shoes = buildTodoTip({ title: '买一双跑鞋 600' })
check('跑鞋待办优先给运动建议',
  shoes.includes('跑鞋') && shoes.includes('热身') && !shoes.includes('取件码'))

const subscription = buildTodoTip({ title: '月底复盘视频会员是否恢复' })
check('会员待办引用原文并给使用记录建议',
  subscription.includes('视频会员') && subscription.includes('使用记录'))

const unknownTodo = buildTodoTip({ title: '整理桌面' })
check('未知待办只基于原文提示补时间或下一步',
  unknownTodo.includes('整理桌面') && /截止时间|下一步/.test(unknownTodo))

console.log(`\n通过 ${passed} 项小知内容点评测试`)
