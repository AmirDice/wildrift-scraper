import type { Locale } from "@/lib/i18n";
import type { Lane } from "@/lib/champion-seo";

/**
 * Interface copy for the translated pages, hand-written per language.
 * Keep it plain and specific: no em dashes, no emojis (site style rule).
 * Functions take already-localized names.
 */
export interface Dict {
  lanes: Record<Lane, string>;
  win: string;
  pick: string;
  winRate: string;
  tier: string;
  role: string;
  champion: string;
  patch: (p: string) => string;
  tierName: (label: string) => string;
  sourceChina: string;
  sourceLadder: string;
  language: string;
  back: (name: string) => string;
  englishPage: string;
  questions: (name: string) => string;
  // home
  homeTitle: string;
  homeDescription: string;
  homeH1: string;
  homeIntro: string;
  topChampions: string;
  fullTierList: string;
  allChampions: string;
  // tier list
  tierTitle: (patch: string) => string;
  tierDescription: string;
  tierH1: string;
  tierIntro: string;
  // champion
  champTitle: (name: string, patch: string) => string;
  champDescription: (name: string, tier: string, wr: string) => string;
  champH1: (name: string) => string;
  topItems: string;
  topItemsDesc: (name: string) => string;
  runesHeading: string;
  strongAgainst: (name: string) => string;
  weakAgainst: (name: string) => string;
  lanesHeading: string;
  // lane
  laneTitle: (name: string, lane: string, patch: string) => string;
  laneDescription: (name: string, lane: string) => string;
  laneH1: (name: string, lane: string) => string;
  itemCores: string;
  itemCoresDesc: string;
  runePages: string;
  spells: string;
  boots: string;
  bootsStale: string;
  matchups: string;
  winsAgainst: (name: string) => string;
  losesTo: (name: string) => string;
  partnersGood: string;
  partnersBad: string;
  alsoPlayed: (name: string) => string;
  // runes
  runesTitle: (name: string, patch: string) => string;
  runesDescription: (name: string) => string;
  runesH1: (name: string) => string;
  whatTopPlayersRun: (name: string) => string;
  ofPlayers: (count: number, players: number) => string;
  minorRunes: string;
  runePagesByLane: string;
  // counters
  countersTitle: (name: string, patch: string) => string;
  countersDescription: (name: string) => string;
  countersH1: (name: string) => string;
  bestCounters: (name: string) => string;
  bestCountersDesc: (name: string) => string;
  beats: (name: string) => string;
  // FAQ
  faqBuildQ: (name: string) => string;
  faqBuildA: (name: string, items: string) => string;
  faqCounterQ: (name: string) => string;
  faqCounterA: (list: string) => string;
  faqRunesQ: (name: string) => string;
  faqRunesA: (keystone: string, count: number, players: number) => string;
  faqGoodQ: (name: string) => string;
  faqGoodA: (name: string, tier: string, wr: string) => string;
  faqLaneBuildQ: (name: string, lane: string) => string;
  faqLaneBuildA: (core: string, pick: string, win: string) => string;
  faqCounterHowQ: (name: string) => string;
  faqCounterHowA: (list: string) => string;
}

const en_lanes = (b: string, j: string, m: string, d: string, s: string): Record<Lane, string> => ({ baron: b, jungle: j, mid: m, dragon: d, support: s });

const zh: Dict = {
  lanes: en_lanes("上单", "打野", "中单", "下路", "辅助"),
  win: "胜率", pick: "登场率", winRate: "胜率", tier: "强度", role: "位置", champion: "英雄",
  patch: (p) => `版本 ${p}`, tierName: (l) => `${l}级`,
  sourceChina: "国服巅峰赛（峡谷之巅）数据", sourceLadder: "欧服与美服各英雄前30名玩家",
  language: "语言", back: (n) => `返回 ${n}`, englishPage: "查看英文完整页面（技能、出装与版本历史）",
  questions: (n) => `${n} 常见问题`,
  homeTitle: "英雄联盟手游 强度榜、出装与符文 | WrTrueMeta",
  homeDescription: "英雄联盟手游（Wild Rift）强度榜、英雄出装、符文与克制关系，数据来自各英雄顶尖玩家与国服巅峰赛。",
  homeH1: "英雄联盟手游 数据与出装",
  homeIntro: "强度榜按各英雄顶尖玩家的真实胜率排序，并提供每个位置的出装、符文与对线克制。",
  topChampions: "当前最强英雄", fullTierList: "查看完整强度榜", allChampions: "全部英雄",
  tierTitle: (p) => `英雄联盟手游 强度榜 版本 ${p} | WrTrueMeta`,
  tierDescription: "按各英雄在欧服与美服前30名玩家的胜率排序的英雄联盟手游强度榜。",
  tierH1: "英雄联盟手游 强度榜",
  tierIntro: "每个英雄的强度来自其排行榜前30名玩家的表现，而不是所有对局的平均值。",
  champTitle: (n, p) => `${n} 出装、符文与克制 英雄联盟手游 版本 ${p} | WrTrueMeta`,
  champDescription: (n, t, wr) => `${n} 在英雄联盟手游中为 ${t}，顶尖玩家胜率 ${wr}。出装、符文、克制与各位置数据。`,
  champH1: (n) => `${n} 出装与符文`,
  topItems: "顶尖玩家常用装备", topItemsDesc: (n) => `欧服与美服 ${n} 顶尖玩家最常完成的装备。`,
  runesHeading: "符文", strongAgainst: (n) => `${n} 克制`, weakAgainst: (n) => `克制 ${n} 的英雄`,
  lanesHeading: "各位置出装",
  laneTitle: (n, l, p) => `${n} ${l} 出装 英雄联盟手游 版本 ${p}：装备、符文与对线 | WrTrueMeta`,
  laneDescription: (n, l) => `${n} ${l} 最常用的核心装备、符文、召唤师技能与对线数据，附胜率与登场率。`,
  laneH1: (n, l) => `${n} ${l} 出装`,
  itemCores: "核心装备", itemCoresDesc: "最常完成的三件核心装备组合，按登场率排序。",
  runePages: "符文页", spells: "召唤师技能", boots: "二级鞋", bootsStale: "旧数据：国服应用自2026年7月起未更新鞋子页面。",
  matchups: "对线数据", winsAgainst: (n) => `${n} 占优的对局`, losesTo: (n) => `${n} 劣势的对局`,
  partnersGood: "最佳搭档", partnersBad: "较差搭档", alsoPlayed: (n) => `${n} 也可以打：`,
  runesTitle: (n, p) => `${n} 符文 英雄联盟手游 版本 ${p}：最佳基石符文与符文页 | WrTrueMeta`,
  runesDescription: (n) => `${n} 顶尖玩家使用的符文，以及各位置最常用的符文页与胜率。`,
  runesH1: (n) => `${n} 符文`,
  whatTopPlayersRun: (n) => `${n} 顶尖玩家的符文选择`, ofPlayers: (c, p) => `${p} 名玩家中 ${c} 名使用`,
  minorRunes: "次要符文", runePagesByLane: "各位置最常用符文页",
  countersTitle: (n, p) => `如何克制 ${n} 英雄联盟手游 版本 ${p} | WrTrueMeta`,
  countersDescription: (n) => `在英雄联盟手游中最常击败 ${n} 的英雄，附对局胜率。`,
  countersH1: (n) => `如何克制 ${n}`,
  bestCounters: (n) => `克制 ${n} 的最佳英雄`, bestCountersDesc: (n) => `数字为 ${n} 在该对局中的胜率，越低对你越有利。`,
  beats: (n) => `${n} 占优的英雄`,
  faqBuildQ: (n) => `${n} 最强出装是什么？`,
  faqBuildA: (n, i) => `${n} 顶尖玩家最常做的装备是：${i}。`,
  faqCounterQ: (n) => `谁克制 ${n}？`, faqCounterA: (l) => `国服巅峰赛中最难打的对局：${l}。`,
  faqRunesQ: (n) => `${n} 带什么符文？`, faqRunesA: (k, c, p) => `${p} 名顶尖玩家中有 ${c} 名使用基石符文 ${k}。`,
  faqGoodQ: (n) => `${n} 现在强吗？`, faqGoodA: (n, t, wr) => `${n} 当前为 ${t}，欧服与美服顶尖玩家胜率 ${wr}。`,
  faqLaneBuildQ: (n, l) => `${n} ${l} 怎么出装？`,
  faqLaneBuildA: (c, pk, w) => `国服巅峰赛最常用的核心装备是 ${c}（登场率 ${pk}，胜率 ${w}）。`,
  faqCounterHowQ: (n) => `用什么英雄克制 ${n}？`, faqCounterHowA: (l) => `${l}。`,
};

const ko: Dict = {
  lanes: en_lanes("바론 라인", "정글", "미드", "드래곤 라인", "서포터"),
  win: "승률", pick: "픽률", winRate: "승률", tier: "티어", role: "포지션", champion: "챔피언",
  patch: (p) => `패치 ${p}`, tierName: (l) => `${l} 티어`,
  sourceChina: "중국 서버 레전더리 랭크", sourceLadder: "EU·NA 챔피언별 상위 30명",
  language: "언어", back: (n) => `${n}(으)로 돌아가기`, englishPage: "영어 전체 페이지 보기 (스킬, 빌드, 패치 기록)",
  questions: (n) => `${n} 자주 묻는 질문`,
  homeTitle: "와일드 리프트 티어 리스트, 빌드, 룬 | WrTrueMeta",
  homeDescription: "와일드 리프트 티어 리스트와 챔피언 빌드, 룬, 카운터. 챔피언별 상위 플레이어와 중국 서버 랭크 데이터 기반.",
  homeH1: "와일드 리프트 통계와 빌드",
  homeIntro: "챔피언별 최상위 플레이어의 실제 승률로 매긴 티어 리스트와 포지션별 빌드, 룬, 상성 정보.",
  topChampions: "현재 최강 챔피언", fullTierList: "전체 티어 리스트 보기", allChampions: "모든 챔피언",
  tierTitle: (p) => `와일드 리프트 티어 리스트 패치 ${p} | WrTrueMeta`,
  tierDescription: "EU와 NA 챔피언별 상위 30명의 승률로 매긴 와일드 리프트 티어 리스트.",
  tierH1: "와일드 리프트 티어 리스트",
  tierIntro: "각 챔피언의 티어는 모든 게임의 평균이 아니라 해당 챔피언 랭킹 상위 30명의 성적으로 정해집니다.",
  champTitle: (n, p) => `${n} 빌드, 룬, 카운터 와일드 리프트 패치 ${p} | WrTrueMeta`,
  champDescription: (n, t, wr) => `와일드 리프트 ${n}: ${t}, 상위 플레이어 승률 ${wr}. 빌드, 룬, 카운터와 포지션별 데이터.`,
  champH1: (n) => `${n} 빌드와 룬`,
  topItems: "상위 플레이어 아이템", topItemsDesc: (n) => `EU·NA ${n} 상위 플레이어가 가장 많이 완성하는 아이템.`,
  runesHeading: "룬", strongAgainst: (n) => `${n}이(가) 강한 상대`, weakAgainst: (n) => `${n}의 카운터`,
  lanesHeading: "포지션별 빌드",
  laneTitle: (n, l, p) => `${n} ${l} 빌드 와일드 리프트 패치 ${p}: 아이템, 룬, 상성 | WrTrueMeta`,
  laneDescription: (n, l) => `${n} ${l}에서 가장 많이 쓰는 코어 아이템, 룬, 소환사 주문과 상성, 승률과 픽률 포함.`,
  laneH1: (n, l) => `${n} ${l} 빌드`,
  itemCores: "코어 아이템", itemCoresDesc: "가장 많이 완성되는 3코어 조합, 픽률 순.",
  runePages: "룬 페이지", spells: "소환사 주문", boots: "신발", bootsStale: "오래된 데이터: 중국 앱의 신발 페이지는 2026년 7월 이후 갱신되지 않았습니다.",
  matchups: "상성", winsAgainst: (n) => `${n}이(가) 이기는 상대`, losesTo: (n) => `${n}이(가) 지는 상대`,
  partnersGood: "잘 맞는 조합", partnersBad: "안 맞는 조합", alsoPlayed: (n) => `${n}은(는) 다음 포지션에서도 플레이됩니다:`,
  runesTitle: (n, p) => `${n} 룬 와일드 리프트 패치 ${p}: 핵심 룬과 룬 페이지 | WrTrueMeta`,
  runesDescription: (n) => `${n} 상위 플레이어가 쓰는 룬과 포지션별로 가장 많이 쓰는 룬 페이지와 승률.`,
  runesH1: (n) => `${n} 룬`,
  whatTopPlayersRun: (n) => `${n} 상위 플레이어의 룬`, ofPlayers: (c, p) => `${p}명 중 ${c}명`,
  minorRunes: "보조 룬", runePagesByLane: "포지션별 인기 룬 페이지",
  countersTitle: (n, p) => `${n} 카운터 방법 와일드 리프트 패치 ${p} | WrTrueMeta`,
  countersDescription: (n) => `와일드 리프트에서 ${n}을(를) 가장 자주 이기는 챔피언과 상대 승률.`,
  countersH1: (n) => `${n} 카운터 방법`,
  bestCounters: (n) => `${n}의 최고 카운터`, bestCountersDesc: (n) => `숫자는 해당 상대에 대한 ${n}의 승률입니다. 낮을수록 유리합니다.`,
  beats: (n) => `${n}이(가) 강한 상대`,
  faqBuildQ: (n) => `${n} 최고의 빌드는?`, faqBuildA: (n, i) => `${n} 상위 플레이어가 가장 많이 사는 아이템: ${i}.`,
  faqCounterQ: (n) => `${n}의 카운터는?`, faqCounterA: (l) => `중국 서버 레전더리 랭크 기준 가장 어려운 상대: ${l}.`,
  faqRunesQ: (n) => `${n} 룬은 무엇을 쓰나요?`, faqRunesA: (k, c, p) => `상위 플레이어 ${p}명 중 ${c}명이 핵심 룬으로 ${k}을(를) 씁니다.`,
  faqGoodQ: (n) => `${n} 지금 좋은가요?`, faqGoodA: (n, t, wr) => `${n}은(는) 현재 ${t}이며 EU·NA 상위 플레이어 승률은 ${wr}입니다.`,
  faqLaneBuildQ: (n, l) => `${n} ${l} 빌드는?`, faqLaneBuildA: (c, pk, w) => `가장 많이 쓰는 코어는 ${c}입니다 (픽률 ${pk}, 승률 ${w}).`,
  faqCounterHowQ: (n) => `${n} 상대로 어떤 챔피언을 고르나요?`, faqCounterHowA: (l) => `${l}.`,
};

const tr: Dict = {
  lanes: en_lanes("Baron Koridoru", "Orman", "Orta Koridor", "Ejderha Koridoru", "Destek"),
  win: "kazanma", pick: "seçilme", winRate: "Kazanma oranı", tier: "Seviye", role: "Rol", champion: "Şampiyon",
  patch: (p) => `Yama ${p}`, tierName: (l) => `${l} seviye`,
  sourceChina: "Çin sunucusu Efsanevi dereceli", sourceLadder: "EU ve NA'da her şampiyonun en iyi 30 oyuncusu",
  language: "Dil", back: (n) => `${n} sayfasına dön`, englishPage: "Tam İngilizce sayfa (yetenekler, buildler ve yama geçmişi)",
  questions: (n) => `${n} hakkında sorular`,
  homeTitle: "Wild Rift Tier List, Buildler ve Rünler | WrTrueMeta",
  homeDescription: "Wild Rift tier list, şampiyon buildleri, rünler ve counter'lar. Her şampiyonun en iyi oyuncuları ve Çin dereceli verileriyle.",
  homeH1: "Wild Rift istatistikleri ve buildler",
  homeIntro: "Her şampiyonun en iyi oyuncularının gerçek kazanma oranına göre sıralanmış tier list, her rol için build, rün ve eşleşmeler.",
  topChampions: "Şu anki en güçlü şampiyonlar", fullTierList: "Tüm tier list'i gör", allChampions: "Tüm şampiyonlar",
  tierTitle: (p) => `Wild Rift Tier List Yama ${p} | WrTrueMeta`,
  tierDescription: "Her şampiyonun EU ve NA'daki en iyi 30 oyuncusunun kazanma oranına göre Wild Rift tier list.",
  tierH1: "Wild Rift Tier List",
  tierIntro: "Her şampiyonun seviyesi, tüm maçların ortalamasından değil, o şampiyonun sıralamasındaki ilk 30 oyuncunun performansından gelir.",
  champTitle: (n, p) => `${n} Build, Rün ve Counter Wild Rift Yama ${p} | WrTrueMeta`,
  champDescription: (n, t, wr) => `Wild Rift'te ${n}: ${t}, en iyi oyuncularında ${wr} kazanma oranı. Build, rün, counter ve rol verileri.`,
  champH1: (n) => `${n} build ve rünler`,
  topItems: "En iyi oyuncuların eşyaları", topItemsDesc: (n) => `EU ve NA'daki en iyi ${n} oyuncularının en çok tamamladığı eşyalar.`,
  runesHeading: "Rünler", strongAgainst: (n) => `${n} şunlara karşı güçlü`, weakAgainst: (n) => `${n} şunlara karşı zayıf`,
  lanesHeading: "Role göre buildler",
  laneTitle: (n, l, p) => `${n} ${l} Build Wild Rift Yama ${p}: Eşyalar, Rünler ve Eşleşmeler | WrTrueMeta`,
  laneDescription: (n, l) => `${n} ${l} için en çok kullanılan çekirdek eşyalar, rünler, büyüler ve eşleşmeler; kazanma ve seçilme oranlarıyla.`,
  laneH1: (n, l) => `${n} ${l} build`,
  itemCores: "Çekirdek eşyalar", itemCoresDesc: "En sık tamamlanan üç eşyalık çekirdekler, seçilme oranına göre.",
  runePages: "Rün sayfaları", spells: "Sihirdar büyüleri", boots: "Botlar", bootsStale: "Eski veri: Çin uygulaması bot sayfasını Temmuz 2026'dan beri güncellemiyor.",
  matchups: "Eşleşmeler", winsAgainst: (n) => `${n} şunları yener`, losesTo: (n) => `${n} şunlara kaybeder`,
  partnersGood: "İyi anlaştığı şampiyonlar", partnersBad: "Zorlandığı şampiyonlar", alsoPlayed: (n) => `${n} ayrıca şurada oynanır:`,
  runesTitle: (n, p) => `${n} Rünleri Wild Rift Yama ${p}: En İyi Ana Rün ve Rün Sayfaları | WrTrueMeta`,
  runesDescription: (n) => `En iyi ${n} oyuncularının kullandığı rünler ve her rol için en çok seçilen rün sayfaları.`,
  runesH1: (n) => `${n} rünleri`,
  whatTopPlayersRun: (n) => `En iyi ${n} oyuncularının rünleri`, ofPlayers: (c, p) => `${p} oyuncudan ${c}`,
  minorRunes: "Yan rünler", runePagesByLane: "Role göre en çok seçilen rün sayfaları",
  countersTitle: (n, p) => `${n} Counter: Wild Rift'te ${n}'e Karşı Ne Seçilir (Yama ${p}) | WrTrueMeta`,
  countersDescription: (n) => `Wild Rift'te ${n}'i en sık yenen şampiyonlar ve eşleşme kazanma oranları.`,
  countersH1: (n) => `${n} nasıl counter'lanır`,
  bestCounters: (n) => `${n}'e karşı en iyi seçimler`, bestCountersDesc: (n) => `Sayı, ${n}'in o eşleşmedeki kazanma oranıdır; düşük olması senin için iyidir.`,
  beats: (n) => `${n}'in yendiği şampiyonlar`,
  faqBuildQ: (n) => `Wild Rift'te en iyi ${n} buildi nedir?`, faqBuildA: (n, i) => `En iyi ${n} oyuncularının en çok kurduğu eşyalar: ${i}.`,
  faqCounterQ: (n) => `${n}'in counter'ı kim?`, faqCounterA: (l) => `Çin Efsanevi derecelide en zor eşleşmeler: ${l}.`,
  faqRunesQ: (n) => `${n} için en iyi rünler hangileri?`, faqRunesA: (k, c, p) => `En iyi ${p} oyuncudan ${c} tanesi ana rün olarak ${k} kullanıyor.`,
  faqGoodQ: (n) => `${n} şu an güçlü mü?`, faqGoodA: (n, t, wr) => `${n} şu anda ${t}; EU ve NA'daki en iyi oyuncularında kazanma oranı ${wr}.`,
  faqLaneBuildQ: (n, l) => `${n} ${l} buildi nedir?`, faqLaneBuildA: (c, pk, w) => `En çok kullanılan çekirdek: ${c} (seçilme ${pk}, kazanma ${w}).`,
  faqCounterHowQ: (n) => `${n}'e karşı kimi seçmeliyim?`, faqCounterHowA: (l) => `${l}.`,
};

const fr: Dict = {
  lanes: en_lanes("Voie du Baron", "Jungle", "Voie du milieu", "Voie du Dragon", "Support"),
  win: "victoires", pick: "choix", winRate: "Taux de victoire", tier: "Tier", role: "Rôle", champion: "Champion",
  patch: (p) => `Patch ${p}`, tierName: (l) => `tier ${l}`,
  sourceChina: "Classé Légendaire, serveur chinois", sourceLadder: "les 30 meilleurs joueurs de chaque champion en EU et NA",
  language: "Langue", back: (n) => `Retour à ${n}`, englishPage: "Page complète en anglais (compétences, builds et historique des patchs)",
  questions: (n) => `Questions sur ${n}`,
  homeTitle: "Wild Rift Tier List, Builds et Runes | WrTrueMeta",
  homeDescription: "Tier list Wild Rift, builds, runes et contres de chaque champion, d'après ses meilleurs joueurs et le classé chinois.",
  homeH1: "Statistiques et builds Wild Rift",
  homeIntro: "Une tier list classée selon le vrai taux de victoire des meilleurs joueurs de chaque champion, avec builds, runes et matchups par rôle.",
  topChampions: "Les champions les plus forts", fullTierList: "Voir la tier list complète", allChampions: "Tous les champions",
  tierTitle: (p) => `Tier List Wild Rift Patch ${p} | WrTrueMeta`,
  tierDescription: "La tier list Wild Rift classée selon le taux de victoire des 30 meilleurs joueurs de chaque champion en EU et NA.",
  tierH1: "Tier list Wild Rift",
  tierIntro: "Le tier de chaque champion vient des 30 meilleurs joueurs de son classement, pas de la moyenne de toutes les parties.",
  champTitle: (n, p) => `${n} Build, Runes et Contres Wild Rift Patch ${p} | WrTrueMeta`,
  champDescription: (n, t, wr) => `${n} dans Wild Rift : ${t}, ${wr} de victoires chez ses meilleurs joueurs. Build, runes, contres et données par rôle.`,
  champH1: (n) => `Build et runes de ${n}`,
  topItems: "Objets des meilleurs joueurs", topItemsDesc: (n) => `Les objets que les meilleurs joueurs de ${n} en EU et NA terminent le plus.`,
  runesHeading: "Runes", strongAgainst: (n) => `${n} est fort contre`, weakAgainst: (n) => `${n} est faible contre`,
  lanesHeading: "Builds par rôle",
  laneTitle: (n, l, p) => `${n} ${l} Build Wild Rift Patch ${p} : Objets, Runes et Matchups | WrTrueMeta`,
  laneDescription: (n, l) => `${n} en ${l} : objets principaux, runes, sorts et matchups les plus joués, avec taux de victoire et de choix.`,
  laneH1: (n, l) => `Build ${n} ${l}`,
  itemCores: "Objets principaux", itemCoresDesc: "Les combinaisons de trois objets les plus terminées, par taux de choix.",
  runePages: "Pages de runes", spells: "Sorts d'invocateur", boots: "Bottes", bootsStale: "Données anciennes : l'application chinoise ne met plus à jour la page des bottes depuis juillet 2026.",
  matchups: "Matchups", winsAgainst: (n) => `${n} gagne contre`, losesTo: (n) => `${n} perd contre`,
  partnersGood: "Bons partenaires", partnersBad: "Partenaires difficiles", alsoPlayed: (n) => `${n} se joue aussi en`,
  runesTitle: (n, p) => `Runes ${n} Wild Rift Patch ${p} : Meilleure Rune Clé et Pages de Runes | WrTrueMeta`,
  runesDescription: (n) => `Les runes des meilleurs joueurs de ${n} et les pages de runes les plus jouées par rôle.`,
  runesH1: (n) => `Runes de ${n}`,
  whatTopPlayersRun: (n) => `Les runes des meilleurs joueurs de ${n}`, ofPlayers: (c, p) => `${c} joueurs sur ${p}`,
  minorRunes: "Runes secondaires", runePagesByLane: "Pages de runes les plus jouées par rôle",
  countersTitle: (n, p) => `Comment contrer ${n} dans Wild Rift (Patch ${p}) | WrTrueMeta`,
  countersDescription: (n) => `Les champions qui battent le plus souvent ${n} dans Wild Rift, avec les taux de victoire des matchups.`,
  countersH1: (n) => `Comment contrer ${n}`,
  bestCounters: (n) => `Meilleurs contres à ${n}`, bestCountersDesc: (n) => `Le chiffre est le taux de victoire de ${n} dans ce matchup : plus il est bas, mieux c'est pour vous.`,
  beats: (n) => `${n} bat`,
  faqBuildQ: (n) => `Quel est le meilleur build de ${n} dans Wild Rift ?`, faqBuildA: (n, i) => `Les objets que les meilleurs joueurs de ${n} construisent le plus : ${i}.`,
  faqCounterQ: (n) => `Qui contre ${n} ?`, faqCounterA: (l) => `Ses matchups les plus difficiles en classé Légendaire chinois : ${l}.`,
  faqRunesQ: (n) => `Quelles runes pour ${n} ?`, faqRunesA: (k, c, p) => `${c} des ${p} meilleurs joueurs prennent ${k} comme rune clé.`,
  faqGoodQ: (n) => `${n} est-il fort en ce moment ?`, faqGoodA: (n, t, wr) => `${n} est ${t}, avec ${wr} de victoires chez ses meilleurs joueurs en EU et NA.`,
  faqLaneBuildQ: (n, l) => `Quel build pour ${n} en ${l} ?`, faqLaneBuildA: (c, pk, w) => `Le cœur le plus joué est ${c} (choix ${pk}, victoires ${w}).`,
  faqCounterHowQ: (n) => `Qui choisir contre ${n} ?`, faqCounterHowA: (l) => `${l}.`,
};

const pl: Dict = {
  lanes: en_lanes("Aleja Barona", "Dżungla", "Środkowa aleja", "Aleja Smoka", "Wsparcie"),
  win: "wygranych", pick: "wyborów", winRate: "Współczynnik wygranych", tier: "Tier", role: "Rola", champion: "Bohater",
  patch: (p) => `Patch ${p}`, tierName: (l) => `tier ${l}`,
  sourceChina: "chiński serwer, ranking Legendarny", sourceLadder: "30 najlepszych graczy każdego bohatera w EU i NA",
  language: "Język", back: (n) => `Wróć do ${n}`, englishPage: "Pełna strona po angielsku (umiejętności, buildy i historia patchy)",
  questions: (n) => `Pytania o ${n}`,
  homeTitle: "Wild Rift Tier List, Buildy i Runy | WrTrueMeta",
  homeDescription: "Tier lista Wild Rift, buildy, runy i kontry każdego bohatera na podstawie najlepszych graczy i chińskich rankingów.",
  homeH1: "Statystyki i buildy Wild Rift",
  homeIntro: "Tier lista ułożona według prawdziwego współczynnika wygranych najlepszych graczy każdego bohatera, z buildami, runami i matchupami dla każdej roli.",
  topChampions: "Najsilniejsi bohaterowie teraz", fullTierList: "Zobacz pełną tier listę", allChampions: "Wszyscy bohaterowie",
  tierTitle: (p) => `Tier Lista Wild Rift Patch ${p} | WrTrueMeta`,
  tierDescription: "Tier lista Wild Rift według współczynnika wygranych 30 najlepszych graczy każdego bohatera w EU i NA.",
  tierH1: "Tier lista Wild Rift",
  tierIntro: "Tier każdego bohatera wynika z wyników 30 najlepszych graczy z jego rankingu, a nie ze średniej ze wszystkich gier.",
  champTitle: (n, p) => `${n} Build, Runy i Kontry Wild Rift Patch ${p} | WrTrueMeta`,
  champDescription: (n, t, wr) => `${n} w Wild Rift: ${t}, ${wr} wygranych u najlepszych graczy. Build, runy, kontry i dane dla każdej roli.`,
  champH1: (n) => `${n}: build i runy`,
  topItems: "Przedmioty najlepszych graczy", topItemsDesc: (n) => `Przedmioty, które najlepsi gracze ${n} w EU i NA kończą najczęściej.`,
  runesHeading: "Runy", strongAgainst: (n) => `${n} jest silny przeciwko`, weakAgainst: (n) => `${n} jest słaby przeciwko`,
  lanesHeading: "Buildy dla ról",
  laneTitle: (n, l, p) => `${n} ${l} Build Wild Rift Patch ${p}: Przedmioty, Runy i Matchupy | WrTrueMeta`,
  laneDescription: (n, l) => `${n} (${l}): najczęściej wybierane przedmioty, runy, czary i matchupy, ze współczynnikiem wygranych i wyborów.`,
  laneH1: (n, l) => `${n} ${l}: build`,
  itemCores: "Główne przedmioty", itemCoresDesc: "Najczęściej kończone zestawy trzech przedmiotów, według częstości wyboru.",
  runePages: "Strony run", spells: "Czary przywoływacza", boots: "Buty", bootsStale: "Stare dane: chińska aplikacja nie aktualizuje strony butów od lipca 2026.",
  matchups: "Matchupy", winsAgainst: (n) => `${n} wygrywa z`, losesTo: (n) => `${n} przegrywa z`,
  partnersGood: "Dobrzy partnerzy", partnersBad: "Trudni partnerzy", alsoPlayed: (n) => `${n} gra się też na:`,
  runesTitle: (n, p) => `Runy ${n} Wild Rift Patch ${p}: Najlepsza Runa Główna i Strony Run | WrTrueMeta`,
  runesDescription: (n) => `Runy najlepszych graczy ${n} i najczęściej wybierane strony run dla każdej roli.`,
  runesH1: (n) => `Runy: ${n}`,
  whatTopPlayersRun: (n) => `Runy najlepszych graczy ${n}`, ofPlayers: (c, p) => `${c} z ${p} graczy`,
  minorRunes: "Runy pomocnicze", runePagesByLane: "Najczęściej wybierane strony run według roli",
  countersTitle: (n, p) => `Jak kontrować ${n} w Wild Rift (Patch ${p}) | WrTrueMeta`,
  countersDescription: (n) => `Bohaterowie, którzy najczęściej wygrywają z ${n} w Wild Rift, ze współczynnikami wygranych.`,
  countersH1: (n) => `Jak kontrować ${n}`,
  bestCounters: (n) => `Najlepsze kontry na ${n}`, bestCountersDesc: (n) => `Liczba to współczynnik wygranych ${n} w tym matchupie: im niższy, tym lepiej dla ciebie.`,
  beats: (n) => `${n} wygrywa z`,
  faqBuildQ: (n) => `Jaki jest najlepszy build ${n} w Wild Rift?`, faqBuildA: (n, i) => `Przedmioty najczęściej budowane przez najlepszych graczy ${n}: ${i}.`,
  faqCounterQ: (n) => `Kto kontruje ${n}?`, faqCounterA: (l) => `Najtrudniejsze matchupy w chińskim rankingu Legendarnym: ${l}.`,
  faqRunesQ: (n) => `Jakie runy dla ${n}?`, faqRunesA: (k, c, p) => `${c} z ${p} najlepszych graczy wybiera ${k} jako runę główną.`,
  faqGoodQ: (n) => `Czy ${n} jest teraz silny?`, faqGoodA: (n, t, wr) => `${n} jest teraz ${t}, z ${wr} wygranych u najlepszych graczy w EU i NA.`,
  faqLaneBuildQ: (n, l) => `Jaki build dla ${n} (${l})?`, faqLaneBuildA: (c, pk, w) => `Najczęściej wybierany zestaw to ${c} (wybory ${pk}, wygrane ${w}).`,
  faqCounterHowQ: (n) => `Kogo wybrać przeciwko ${n}?`, faqCounterHowA: (l) => `${l}.`,
};

const es: Dict = {
  lanes: en_lanes("Línea del Barón", "Jungla", "Línea central", "Línea del Dragón", "Soporte"),
  win: "victorias", pick: "elección", winRate: "Tasa de victoria", tier: "Tier", role: "Rol", champion: "Campeón",
  patch: (p) => `Parche ${p}`, tierName: (l) => `tier ${l}`,
  sourceChina: "clasificatoria Legendaria del servidor chino", sourceLadder: "los 30 mejores jugadores de cada campeón en EU y NA",
  language: "Idioma", back: (n) => `Volver a ${n}`, englishPage: "Página completa en inglés (habilidades, builds e historial de parches)",
  questions: (n) => `Preguntas sobre ${n}`,
  homeTitle: "Wild Rift Tier List, Builds y Runas | WrTrueMeta",
  homeDescription: "Tier list de Wild Rift, builds, runas y counters de cada campeón, según sus mejores jugadores y la clasificatoria china.",
  homeH1: "Estadísticas y builds de Wild Rift",
  homeIntro: "Una tier list ordenada por la tasa de victoria real de los mejores jugadores de cada campeón, con builds, runas y enfrentamientos por rol.",
  topChampions: "Los campeones más fuertes ahora", fullTierList: "Ver la tier list completa", allChampions: "Todos los campeones",
  tierTitle: (p) => `Tier List de Wild Rift Parche ${p} | WrTrueMeta`,
  tierDescription: "La tier list de Wild Rift según la tasa de victoria de los 30 mejores jugadores de cada campeón en EU y NA.",
  tierH1: "Tier list de Wild Rift",
  tierIntro: "El tier de cada campeón sale de los 30 mejores jugadores de su clasificación, no del promedio de todas las partidas.",
  champTitle: (n, p) => `${n} Build, Runas y Counters Wild Rift Parche ${p} | WrTrueMeta`,
  champDescription: (n, t, wr) => `${n} en Wild Rift: ${t}, ${wr} de victorias entre sus mejores jugadores. Build, runas, counters y datos por rol.`,
  champH1: (n) => `Build y runas de ${n}`,
  topItems: "Objetos de los mejores jugadores", topItemsDesc: (n) => `Los objetos que más completan los mejores jugadores de ${n} en EU y NA.`,
  runesHeading: "Runas", strongAgainst: (n) => `${n} es fuerte contra`, weakAgainst: (n) => `${n} es débil contra`,
  lanesHeading: "Builds por rol",
  laneTitle: (n, l, p) => `${n} ${l} Build Wild Rift Parche ${p}: Objetos, Runas y Enfrentamientos | WrTrueMeta`,
  laneDescription: (n, l) => `${n} en ${l}: objetos principales, runas, hechizos y enfrentamientos más jugados, con tasas de victoria y elección.`,
  laneH1: (n, l) => `Build de ${n} ${l}`,
  itemCores: "Objetos principales", itemCoresDesc: "Las combinaciones de tres objetos más completadas, por tasa de elección.",
  runePages: "Páginas de runas", spells: "Hechizos de invocador", boots: "Botas", bootsStale: "Datos antiguos: la app china no actualiza su página de botas desde julio de 2026.",
  matchups: "Enfrentamientos", winsAgainst: (n) => `${n} gana contra`, losesTo: (n) => `${n} pierde contra`,
  partnersGood: "Buenos compañeros", partnersBad: "Compañeros difíciles", alsoPlayed: (n) => `${n} también se juega en`,
  runesTitle: (n, p) => `Runas de ${n} Wild Rift Parche ${p}: Mejor Runa Clave y Páginas de Runas | WrTrueMeta`,
  runesDescription: (n) => `Las runas de los mejores jugadores de ${n} y las páginas de runas más jugadas por rol.`,
  runesH1: (n) => `Runas de ${n}`,
  whatTopPlayersRun: (n) => `Las runas de los mejores jugadores de ${n}`, ofPlayers: (c, p) => `${c} de ${p} jugadores`,
  minorRunes: "Runas secundarias", runePagesByLane: "Páginas de runas más jugadas por rol",
  countersTitle: (n, p) => `Cómo counterear a ${n} en Wild Rift (Parche ${p}) | WrTrueMeta`,
  countersDescription: (n) => `Los campeones que más veces vencen a ${n} en Wild Rift, con la tasa de victoria de cada enfrentamiento.`,
  countersH1: (n) => `Cómo counterear a ${n}`,
  bestCounters: (n) => `Mejores counters de ${n}`, bestCountersDesc: (n) => `El número es la tasa de victoria de ${n} en ese enfrentamiento: cuanto más baja, mejor para ti.`,
  beats: (n) => `${n} vence a`,
  faqBuildQ: (n) => `¿Cuál es la mejor build de ${n} en Wild Rift?`, faqBuildA: (n, i) => `Los objetos que más construyen los mejores jugadores de ${n}: ${i}.`,
  faqCounterQ: (n) => `¿Quién counterea a ${n}?`, faqCounterA: (l) => `Sus enfrentamientos más difíciles en la clasificatoria Legendaria china: ${l}.`,
  faqRunesQ: (n) => `¿Qué runas lleva ${n}?`, faqRunesA: (k, c, p) => `${c} de los ${p} mejores jugadores usan ${k} como runa clave.`,
  faqGoodQ: (n) => `¿Es ${n} fuerte ahora?`, faqGoodA: (n, t, wr) => `${n} es ${t}, con ${wr} de victorias entre sus mejores jugadores en EU y NA.`,
  faqLaneBuildQ: (n, l) => `¿Qué build para ${n} en ${l}?`, faqLaneBuildA: (c, pk, w) => `El núcleo más jugado es ${c} (elección ${pk}, victorias ${w}).`,
  faqCounterHowQ: (n) => `¿Qué campeón elegir contra ${n}?`, faqCounterHowA: (l) => `${l}.`,
};

export const DICTS: Record<Locale, Dict> = { zh, ko, tr, fr, pl, es };
export const dict = (lang: Locale): Dict => DICTS[lang];
