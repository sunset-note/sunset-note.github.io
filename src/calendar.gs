// sunset의 투자노트: 공모주 일정을 내 구글 캘린더에 자동 등록 (구글 Apps Script, 맥미니 없이 매시간 실행)
// - 후보: https://sunset-note.github.io/cal.json 의 events (GitHub 자동 갱신이 매시간 만든다)
// - 등록 대상: 균등·비례·대출 등급(graded)이거나 사이트에서 ★로 고른 종목(중계 서버 /mine)
// - 한 번 등록한 일정은 스크립트 속성 'done'에 기록해 다시 만들지 않는다
// 처음 한 번 setup()을 실행하면 매시간 sync()가 돌도록 예약된다.

const CAL_URL = 'https://sunset-note.github.io/cal.json';
const MINE_URL = 'https://sunset-fx.ghlckd01.workers.dev/mine';
// 맥미니에서 이미 등록한 일정(중복 방지)
const DONE0 = {'2339': '2026-10-31', '2338': '2026-10-31', 'L2339': '2026-10-31', 'L2338': '2026-10-31'};

function sync() {
  const cal = JSON.parse(UrlFetchApp.fetch(CAL_URL + '?t=' + Date.now()).getContentText());
  let mine = [];
  try { mine = JSON.parse(UrlFetchApp.fetch(MINE_URL).getContentText()).mine || []; } catch (e) {}
  const P = PropertiesService.getScriptProperties();
  const done = Object.assign({}, DONE0, JSON.parse(P.getProperty('done') || '{}'));
  const today = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  const made = [];
  for (const e of cal.events || []) {
    if (!(e.graded || mine.indexOf(e.ipo) >= 0) || done[e.no]) continue;
    const ev = CalendarApp.getDefaultCalendar().createEvent(e.summary,
      new Date(e.startTime + '+09:00'), new Date(e.endTime + '+09:00'), {description: e.description});
    ev.setColor(String(e.colorId));
    ev.removeAllReminders();
    for (const m of e.reminders) ev.addPopupReminder(m);
    done[e.no] = today;
    made.push(e.summary);
  }
  // 40일 지난 기록은 정리
  const old = Utilities.formatDate(new Date(Date.now() - 40 * 864e5), 'Asia/Seoul', 'yyyy-MM-dd');
  for (const k in done) if (done[k] < old) delete done[k];
  P.setProperty('done', JSON.stringify(done));
  console.log(made.length ? '캘린더 등록: ' + made.join(', ') : '캘린더 OK');
}

function setup() {
  for (const t of ScriptApp.getProjectTriggers()) ScriptApp.deleteTrigger(t);
  ScriptApp.newTrigger('sync').timeBased().everyHours(1).create();
  sync();
}
