import type { SiteLanguage } from "@/lib/preferred-language";

/**
 * Nav copy per language, keyed by the English string the nav is written in
 * (components/site-nav.tsx). Kept free of the localized-names table so the
 * client bundle stays small. A missing key falls back to English.
 */
type Table = Record<string, string>;

const zh: Table = {
  "Tier List": "强度榜", "Champions": "英雄", "Players": "玩家", "Leaderboards": "排行榜",
  "The top players on every champion": "每个英雄的顶尖玩家", "Player Search": "玩家搜索",
  "Find a player and every champion they rank on": "查找玩家及其上榜的所有英雄",
  "Builds": "出装", "Build Studio": "出装工作室", "Generate by playstyle or craft with live stats": "按玩法生成出装，或用实时属性自行搭配",
  "Build vs Enemy Team": "针对敌方阵容出装", "The build that beats their exact five picks": "针对对方五个英雄的出装",
  "Draft Assistant": "选人助手", "Bans, picks and the counter build, live in lobby": "禁用、选人与针对出装，实时辅助",
  "Draft Overlay": "选人悬浮窗", "The draft assistant on top of the game, via our Discord": "在游戏上方显示的选人助手，通过我们的 Discord 获取",
  "Build Albums": "出装收藏", "Save builds & blend with a friend": "保存出装并与好友合并",
  "Items": "装备", "Stats, passives & costs": "属性、被动与价格", "Runes & Spells": "符文与技能",
  "Effects, trees, cooldowns & uses": "效果、系别、冷却与用途", "Meta": "版本", "Meta Overview": "版本概览",
  "Trends, consistency & one-trick picks": "趋势、稳定性与绝活英雄", "Patch Movers": "版本涨跌",
  "Biggest winners & losers right now": "当前变化最大的英雄", "Regions & Brackets": "地区与段位",
  "EU vs NA vs China, and by skill bracket": "欧服、美服与国服，以及各段位", "Compare Champions": "英雄对比",
  "Two champions side by side": "两个英雄并排对比", "Updates": "更新", "Site Updates": "网站更新",
  "What patch the data is on, and email alerts": "数据所属版本与邮件提醒", "Guides": "攻略",
  "Best picks per role, climbing & meta reads": "各位置最佳选择、上分与版本解读", "Balance Report": "平衡报告",
  "Most changed & never changed": "改动最多与从未改动", "Join our Discord": "加入我们的 Discord",
  "Buy me a coffee": "请我喝杯咖啡", "Language": "语言", "Search champions": "搜索英雄", "Toggle menu": "菜单",
};

const vi: Table = {
  "Tier List": "Bảng xếp hạng", "Champions": "Tướng", "Players": "Người chơi", "Leaderboards": "Bảng xếp hạng người chơi",
  "The top players on every champion": "Người chơi giỏi nhất của mỗi tướng", "Player Search": "Tìm người chơi",
  "Find a player and every champion they rank on": "Tìm người chơi và mọi tướng họ có thứ hạng",
  "Builds": "Lên đồ", "Build Studio": "Build Studio", "Generate by playstyle or craft with live stats": "Tạo lối lên đồ theo lối chơi hoặc tự ghép với chỉ số trực tiếp",
  "Build vs Enemy Team": "Lên đồ theo đội địch", "The build that beats their exact five picks": "Lối lên đồ khắc chế đúng năm tướng của đối thủ",
  "Draft Assistant": "Trợ lý cấm chọn", "Bans, picks and the counter build, live in lobby": "Cấm, chọn và lên đồ khắc chế ngay trong phòng chờ",
  "Draft Overlay": "Lớp phủ cấm chọn", "The draft assistant on top of the game, via our Discord": "Trợ lý cấm chọn hiển thị trên trò chơi, qua Discord của chúng tôi",
  "Build Albums": "Bộ sưu tập lối lên đồ", "Save builds & blend with a friend": "Lưu lối lên đồ và kết hợp với bạn bè",
  "Items": "Trang bị", "Stats, passives & costs": "Chỉ số, nội tại và giá", "Runes & Spells": "Ngọc và phép bổ trợ",
  "Effects, trees, cooldowns & uses": "Hiệu ứng, nhánh ngọc, hồi chiêu và cách dùng", "Meta": "Meta", "Meta Overview": "Tổng quan meta",
  "Trends, consistency & one-trick picks": "Xu hướng, độ ổn định và tướng tủ", "Patch Movers": "Biến động phiên bản",
  "Biggest winners & losers right now": "Tướng tăng và giảm mạnh nhất hiện tại", "Regions & Brackets": "Khu vực và bậc rank",
  "EU vs NA vs China, and by skill bracket": "EU, NA và Trung Quốc, theo từng bậc rank", "Compare Champions": "So sánh tướng",
  "Two champions side by side": "Hai tướng đặt cạnh nhau", "Updates": "Cập nhật", "Site Updates": "Cập nhật trang web",
  "What patch the data is on, and email alerts": "Dữ liệu thuộc phiên bản nào, và thông báo qua email", "Guides": "Hướng dẫn",
  "Best picks per role, climbing & meta reads": "Tướng tốt nhất theo vị trí, leo rank và phân tích meta", "Balance Report": "Báo cáo cân bằng",
  "Most changed & never changed": "Thay đổi nhiều nhất và chưa từng thay đổi", "Join our Discord": "Tham gia Discord của chúng tôi",
  "Buy me a coffee": "Mời tôi một ly cà phê", "Language": "Ngôn ngữ", "Search champions": "Tìm tướng", "Toggle menu": "Menu",
};

const tr: Table = {
  "Tier List": "Tier List", "Champions": "Şampiyonlar", "Players": "Oyuncular", "Leaderboards": "Sıralamalar",
  "The top players on every champion": "Her şampiyonun en iyi oyuncuları", "Player Search": "Oyuncu Ara",
  "Find a player and every champion they rank on": "Bir oyuncuyu ve sıralamada olduğu tüm şampiyonları bul",
  "Builds": "Buildler", "Build Studio": "Build Studio", "Generate by playstyle or craft with live stats": "Oyun tarzına göre oluştur ya da canlı istatistiklerle kendin kur",
  "Build vs Enemy Team": "Rakip Takıma Göre Build", "The build that beats their exact five picks": "Rakibin beş seçimini yenen build",
  "Draft Assistant": "Seçim Asistanı", "Bans, picks and the counter build, live in lobby": "Yasaklar, seçimler ve counter build, lobide canlı",
  "Draft Overlay": "Seçim Katmanı", "The draft assistant on top of the game, via our Discord": "Oyunun üstünde seçim asistanı, Discord'umuz üzerinden",
  "Build Albums": "Build Albümleri", "Save builds & blend with a friend": "Buildleri kaydet ve arkadaşınla birleştir",
  "Items": "Eşyalar", "Stats, passives & costs": "İstatistikler, pasifler ve fiyatlar", "Runes & Spells": "Rünler ve Büyüler",
  "Effects, trees, cooldowns & uses": "Etkiler, ağaçlar, bekleme süreleri ve kullanımlar", "Meta": "Meta", "Meta Overview": "Meta Özeti",
  "Trends, consistency & one-trick picks": "Trendler, istikrar ve tek şampiyon uzmanları", "Patch Movers": "Yamada Yükselenler",
  "Biggest winners & losers right now": "Şu an en çok yükselen ve düşenler", "Regions & Brackets": "Bölgeler ve Ligler",
  "EU vs NA vs China, and by skill bracket": "EU, NA ve Çin, lig seviyesine göre", "Compare Champions": "Şampiyon Karşılaştır",
  "Two champions side by side": "İki şampiyon yan yana", "Updates": "Güncellemeler", "Site Updates": "Site Güncellemeleri",
  "What patch the data is on, and email alerts": "Verinin hangi yamada olduğu ve e-posta uyarıları", "Guides": "Rehberler",
  "Best picks per role, climbing & meta reads": "Role göre en iyi seçimler, lig atlama ve meta yorumları", "Balance Report": "Denge Raporu",
  "Most changed & never changed": "En çok değişenler ve hiç değişmeyenler", "Join our Discord": "Discord'umuza katıl",
  "Buy me a coffee": "Bana bir kahve ısmarla", "Language": "Dil", "Search champions": "Şampiyon ara", "Toggle menu": "Menü",
};

const fr: Table = {
  "Tier List": "Tier List", "Champions": "Champions", "Players": "Joueurs", "Leaderboards": "Classements",
  "The top players on every champion": "Les meilleurs joueurs de chaque champion", "Player Search": "Recherche de joueur",
  "Find a player and every champion they rank on": "Trouver un joueur et tous les champions où il est classé",
  "Builds": "Builds", "Build Studio": "Build Studio", "Generate by playstyle or craft with live stats": "Générer selon votre style ou composer avec les stats en direct",
  "Build vs Enemy Team": "Build contre l'équipe adverse", "The build that beats their exact five picks": "Le build qui bat leurs cinq choix",
  "Draft Assistant": "Assistant de draft", "Bans, picks and the counter build, live in lobby": "Bans, choix et build de contre, en direct dans le salon",
  "Draft Overlay": "Overlay de draft", "The draft assistant on top of the game, via our Discord": "L'assistant de draft par-dessus le jeu, via notre Discord",
  "Build Albums": "Albums de builds", "Save builds & blend with a friend": "Enregistrez des builds et combinez-les avec un ami",
  "Items": "Objets", "Stats, passives & costs": "Stats, passifs et coûts", "Runes & Spells": "Runes et sorts",
  "Effects, trees, cooldowns & uses": "Effets, arbres, délais et usages", "Meta": "Méta", "Meta Overview": "Aperçu de la méta",
  "Trends, consistency & one-trick picks": "Tendances, régularité et one-tricks", "Patch Movers": "Évolutions du patch",
  "Biggest winners & losers right now": "Les plus grands gagnants et perdants du moment", "Regions & Brackets": "Régions et rangs",
  "EU vs NA vs China, and by skill bracket": "EU, NA et Chine, par niveau de rang", "Compare Champions": "Comparer des champions",
  "Two champions side by side": "Deux champions côte à côte", "Updates": "Nouveautés", "Site Updates": "Nouveautés du site",
  "What patch the data is on, and email alerts": "Le patch des données, et les alertes par e-mail", "Guides": "Guides",
  "Best picks per role, climbing & meta reads": "Meilleurs choix par rôle, montée en rang et analyses de méta", "Balance Report": "Rapport d'équilibrage",
  "Most changed & never changed": "Les plus modifiés et jamais modifiés", "Join our Discord": "Rejoindre notre Discord",
  "Buy me a coffee": "Offrez-moi un café", "Language": "Langue", "Search champions": "Rechercher un champion", "Toggle menu": "Menu",
};

const pl: Table = {
  "Tier List": "Tier lista", "Champions": "Bohaterowie", "Players": "Gracze", "Leaderboards": "Rankingi",
  "The top players on every champion": "Najlepsi gracze każdego bohatera", "Player Search": "Wyszukaj gracza",
  "Find a player and every champion they rank on": "Znajdź gracza i wszystkich bohaterów, na których jest w rankingu",
  "Builds": "Buildy", "Build Studio": "Build Studio", "Generate by playstyle or craft with live stats": "Generuj według stylu gry lub składaj z bieżącymi statystykami",
  "Build vs Enemy Team": "Build na drużynę wroga", "The build that beats their exact five picks": "Build, który pokonuje ich pięć wyborów",
  "Draft Assistant": "Asystent draftu", "Bans, picks and the counter build, live in lobby": "Bany, wybory i kontr-build na żywo w lobby",
  "Draft Overlay": "Nakładka draftu", "The draft assistant on top of the game, via our Discord": "Asystent draftu na grze, przez nasz Discord",
  "Build Albums": "Albumy buildów", "Save builds & blend with a friend": "Zapisuj buildy i łącz je ze znajomym",
  "Items": "Przedmioty", "Stats, passives & costs": "Statystyki, pasywki i koszty", "Runes & Spells": "Runy i czary",
  "Effects, trees, cooldowns & uses": "Efekty, drzewka, czasy odnowienia i zastosowania", "Meta": "Meta", "Meta Overview": "Przegląd mety",
  "Trends, consistency & one-trick picks": "Trendy, stabilność i one-tricki", "Patch Movers": "Zmiany w patchu",
  "Biggest winners & losers right now": "Największe wzrosty i spadki teraz", "Regions & Brackets": "Regiony i rangi",
  "EU vs NA vs China, and by skill bracket": "EU, NA i Chiny, według poziomu rangi", "Compare Champions": "Porównaj bohaterów",
  "Two champions side by side": "Dwóch bohaterów obok siebie", "Updates": "Aktualizacje", "Site Updates": "Aktualizacje strony",
  "What patch the data is on, and email alerts": "Z którego patcha są dane, i powiadomienia e-mail", "Guides": "Poradniki",
  "Best picks per role, climbing & meta reads": "Najlepsze wybory na rolę, wspinaczka i analizy mety", "Balance Report": "Raport balansu",
  "Most changed & never changed": "Najczęściej i nigdy nie zmieniani", "Join our Discord": "Dołącz do naszego Discorda",
  "Buy me a coffee": "Postaw mi kawę", "Language": "Język", "Search champions": "Szukaj bohatera", "Toggle menu": "Menu",
};

const ko: Table = {
  "Tier List": "티어 리스트", "Champions": "챔피언", "Players": "플레이어", "Leaderboards": "랭킹",
  "The top players on every champion": "챔피언별 최상위 플레이어", "Player Search": "플레이어 검색",
  "Find a player and every champion they rank on": "플레이어와 랭킹에 오른 모든 챔피언 찾기",
  "Builds": "빌드", "Build Studio": "빌드 스튜디오", "Generate by playstyle or craft with live stats": "플레이스타일로 생성하거나 실시간 스탯으로 직접 구성",
  "Build vs Enemy Team": "상대 팀 맞춤 빌드", "The build that beats their exact five picks": "상대 다섯 챔피언을 이기는 빌드",
  "Draft Assistant": "밴픽 도우미", "Bans, picks and the counter build, live in lobby": "대기실에서 실시간으로 밴, 픽, 카운터 빌드",
  "Draft Overlay": "밴픽 오버레이", "The draft assistant on top of the game, via our Discord": "게임 위에 띄우는 밴픽 도우미, 디스코드에서 제공",
  "Build Albums": "빌드 앨범", "Save builds & blend with a friend": "빌드를 저장하고 친구와 합치기",
  "Items": "아이템", "Stats, passives & costs": "스탯, 기본 지속 효과, 가격", "Runes & Spells": "룬과 주문",
  "Effects, trees, cooldowns & uses": "효과, 계열, 재사용 대기시간, 활용", "Meta": "메타", "Meta Overview": "메타 개요",
  "Trends, consistency & one-trick picks": "트렌드, 안정성, 장인 챔피언", "Patch Movers": "패치 변동",
  "Biggest winners & losers right now": "현재 가장 크게 오르고 내린 챔피언", "Regions & Brackets": "지역과 티어 구간",
  "EU vs NA vs China, and by skill bracket": "EU, NA, 중국, 그리고 티어 구간별", "Compare Champions": "챔피언 비교",
  "Two champions side by side": "두 챔피언 나란히 비교", "Updates": "업데이트", "Site Updates": "사이트 업데이트",
  "What patch the data is on, and email alerts": "데이터 기준 패치와 이메일 알림", "Guides": "가이드",
  "Best picks per role, climbing & meta reads": "포지션별 추천 픽, 랭크 올리기, 메타 분석", "Balance Report": "밸런스 리포트",
  "Most changed & never changed": "가장 많이 바뀐 챔피언과 한 번도 안 바뀐 챔피언", "Join our Discord": "디스코드 참여하기",
  "Buy me a coffee": "커피 한 잔 사주기", "Language": "언어", "Search champions": "챔피언 검색", "Toggle menu": "메뉴",
};

const es: Table = {
  "Tier List": "Tier List", "Champions": "Campeones", "Players": "Jugadores", "Leaderboards": "Clasificaciones",
  "The top players on every champion": "Los mejores jugadores de cada campeón", "Player Search": "Buscar jugador",
  "Find a player and every champion they rank on": "Encuentra un jugador y todos los campeones en los que está clasificado",
  "Builds": "Builds", "Build Studio": "Build Studio", "Generate by playstyle or craft with live stats": "Genera según tu estilo o arma la build con estadísticas en vivo",
  "Build vs Enemy Team": "Build contra el equipo rival", "The build that beats their exact five picks": "La build que vence a sus cinco elecciones",
  "Draft Assistant": "Asistente de draft", "Bans, picks and the counter build, live in lobby": "Bans, elecciones y build de counter, en vivo en la sala",
  "Draft Overlay": "Overlay de draft", "The draft assistant on top of the game, via our Discord": "El asistente de draft sobre el juego, a través de nuestro Discord",
  "Build Albums": "Álbumes de builds", "Save builds & blend with a friend": "Guarda builds y combínalas con un amigo",
  "Items": "Objetos", "Stats, passives & costs": "Estadísticas, pasivas y costes", "Runes & Spells": "Runas y hechizos",
  "Effects, trees, cooldowns & uses": "Efectos, ramas, enfriamientos y usos", "Meta": "Meta", "Meta Overview": "Resumen del meta",
  "Trends, consistency & one-trick picks": "Tendencias, regularidad y one-tricks", "Patch Movers": "Cambios del parche",
  "Biggest winners & losers right now": "Los que más suben y bajan ahora", "Regions & Brackets": "Regiones y rangos",
  "EU vs NA vs China, and by skill bracket": "EU, NA y China, por nivel de rango", "Compare Champions": "Comparar campeones",
  "Two champions side by side": "Dos campeones lado a lado", "Updates": "Novedades", "Site Updates": "Novedades del sitio",
  "What patch the data is on, and email alerts": "En qué parche están los datos, y alertas por email", "Guides": "Guías",
  "Best picks per role, climbing & meta reads": "Mejores elecciones por rol, subir de rango y análisis del meta", "Balance Report": "Informe de balance",
  "Most changed & never changed": "Los más cambiados y los nunca cambiados", "Join our Discord": "Únete a nuestro Discord",
  "Buy me a coffee": "Invítame a un café", "Language": "Idioma", "Search champions": "Buscar campeón", "Toggle menu": "Menú",
};

const TABLES: Partial<Record<SiteLanguage, Table>> = { zh, vi, tr, fr, pl, ko, es };

export function navT(lang: SiteLanguage, english: string): string {
  return TABLES[lang]?.[english] ?? english;
}

/** English paths that have a translated version at /<lang><path>. */
export function localizedNavHref(lang: SiteLanguage, href: string): string {
  if (lang === "en") return href;
  if (href === "/" || href === "/tier-list" || href === "/champions") return `/${lang}${href === "/" ? "" : href}`;
  return href;
}
