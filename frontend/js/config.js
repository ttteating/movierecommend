/* ============================================================
 * 智影 · 大数据电影推荐系统 —— 全局配置
 * 修改本文件即可完成与真实后端的对接配置
 * ============================================================ */
window.APP_CONFIG = {
  /* FastAPI 后端地址（Base URL），部署时改为实际地址 */
  API_BASE_URL: 'http://127.0.0.1:8000',

  /* 数据模式：
   *   'auto'  —— 自动探测：后端可达则走真实接口，不可达自动切换内置 Mock（默认，推荐）
   *   'real'  —— 强制真实接口
   *   'mock'  —— 强制演示模式（不请求后端）
   */
  DATA_MODE: 'auto',

  /* 探测后端健康检查的超时时间（毫秒） */
  PROBE_TIMEOUT: 2500,

  /* 演示模式下模拟的网络延迟区间（毫秒） */
  MOCK_LATENCY: [180, 460],

  /* 标准 MovieLens 18 大电影分类（顺序即真实后端的 category_id 顺序，
   * 若数据库 categoryid 顺序不同，请调整本数组顺序） */
  GENRES: [
    { key: 'Action',        cn: '动作',      en: 'Action' },
    { key: 'Adventure',     cn: '冒险',      en: 'Adventure' },
    { key: 'Animation',     cn: '动画',      en: 'Animation' },
    { key: "Children's",    cn: '儿童',      en: "Children's" },
    { key: 'Comedy',        cn: '喜剧',      en: 'Comedy' },
    { key: 'Crime',         cn: '犯罪',      en: 'Crime' },
    { key: 'Documentary',   cn: '纪录片',    en: 'Documentary' },
    { key: 'Drama',         cn: '剧情',      en: 'Drama' },
    { key: 'Fantasy',       cn: '奇幻',      en: 'Fantasy' },
    { key: 'Film-Noir',     cn: '黑色电影',  en: 'Film-Noir' },
    { key: 'Horror',        cn: '恐怖',      en: 'Horror' },
    { key: 'Musical',       cn: '音乐/歌舞', en: 'Musical' },
    { key: 'Mystery',       cn: '悬疑',      en: 'Mystery' },
    { key: 'Romance',       cn: '爱情',      en: 'Romance' },
    { key: 'Sci-Fi',        cn: '科幻',      en: 'Sci-Fi' },
    { key: 'Thriller',      cn: '惊悚',      en: 'Thriller' },
    { key: 'War',           cn: '战争',      en: 'War' },
    { key: 'Western',       cn: '西部',      en: 'Western' }
  ],

  /* 首页巨幕轮播自动切换间隔（毫秒） */
  HERO_INTERVAL: 5000,

  /* 每屏海报数量基准（横滑轨道） */
  RAIL_PER_PAGE: 6
};

/* 类型别名 → 标准 18 分类（用于 typelist 归一化） */
window.GENRE_ALIASES = {
  'Science Fiction': 'Sci-Fi',
  'SciFi': 'Sci-Fi',
  'Childrens': "Children's",
  'Children': "Children's",
  'Film Noir': 'Film-Noir',
  'FilmNoir': 'Film-Noir',
  'Music': 'Musical'
};

/* ============================================================
 * 真实数据库（movierecommend_test.sql 导出）中的分类表内容
 * categoryid 1-22；演示模式（Mock）直接镜像这 22 个分类
 * ============================================================ */
window.REAL_CATEGORIES = [
  { categoryid: 1, name: 'Animation' },
  { categoryid: 2, name: 'Comedy' },
  { categoryid: 3, name: 'Family' },
  { categoryid: 4, name: 'Adventure' },
  { categoryid: 5, name: 'Fantasy' },
  { categoryid: 6, name: 'Romance' },
  { categoryid: 7, name: 'Drama' },
  { categoryid: 8, name: 'Action' },
  { categoryid: 9, name: 'Crime' },
  { categoryid: 10, name: 'Thriller' },
  { categoryid: 11, name: 'Horror' },
  { categoryid: 12, name: 'Science Fiction' },
  { categoryid: 13, name: 'Mystery' },
  { categoryid: 14, name: 'History' },
  { categoryid: 15, name: 'War' },
  { categoryid: 16, name: 'Foreign' },
  { categoryid: 17, name: 'Music' },
  { categoryid: 18, name: 'Documentary' },
  { categoryid: 19, name: 'Western' },
  { categoryid: 20, name: 'TV Movie' },
  { categoryid: 21, name: 'Neo-noir' },
  { categoryid: 22, name: 'Indie' }
];

/* typelist 常见写法 → 真实分类名（用于演示模式映射与兜底） */
window.GENRE_TO_REAL = {
  'Animation': 'Animation', 'Comedy': 'Comedy', 'Family': 'Family',
  'Adventure': 'Adventure', 'Fantasy': 'Fantasy', 'Romance': 'Romance',
  'Drama': 'Drama', 'Action': 'Action', 'Crime': 'Crime',
  'Thriller': 'Thriller', 'Horror': 'Horror',
  'Science Fiction': 'Science Fiction', 'Sci-Fi': 'Science Fiction', 'SciFi': 'Science Fiction',
  'Mystery': 'Mystery', 'History': 'History', 'War': 'War',
  'Foreign': 'Foreign', 'Music': 'Music', 'Musical': 'Music',
  'Documentary': 'Documentary', 'Western': 'Western',
  'TV Movie': 'TV Movie', 'TVMovie': 'TV Movie',
  'Neo-noir': 'Neo-noir', 'Film-Noir': 'Neo-noir', 'FilmNoir': 'Neo-noir', 'Noir': 'Neo-noir',
  'Indie': 'Indie',
  "Children's": 'Family', 'Childrens': 'Family', 'Children': 'Family'
};

/* ============================================================
 * 中文片名 → 英文片名（搜索用）
 * 数据库 movieinfo.moviename 为英文 TMDB 片名，后端按英文字段搜索。
 * 用户输入中文片名时，前端先用本映射翻译成英文再请求后端。
 * 自动映射还包含 mock-data.js 中 69 部电影的中英文名；这里补充其余经典影片。
 * ============================================================ */
window.ZH2EN_EXTRA = {
  '阿凡达': 'Avatar',
  '泰坦尼克号': 'Titanic',
  '泰坦尼克': 'Titanic',
  '变形金刚': 'Transformers',
  '复仇者联盟': 'The Avengers',
  '蜘蛛侠': 'Spider-Man',
  '钢铁侠': 'Iron Man',
  '蝙蝠侠': 'Batman Begins',
  '蝙蝠侠黑暗骑士': 'The Dark Knight',
  '黑暗骑士': 'The Dark Knight',
  '哈利波特': 'Harry Potter and the Philosopher\'s Stone',
  '哈利·波特': 'Harry Potter and the Philosopher\'s Stone',
  '指环王': 'The Lord of the Rings: The Fellowship of the Ring',
  '魔戒': 'The Lord of the Rings: The Fellowship of the Ring',
  '辛德勒的名单': 'Schindler\'s List',
  '拯救大兵瑞恩': 'Saving Private Ryan',
  '无间道风云': 'The Departed',
  '好家伙': 'Goodfellas',
  '非常嫌疑犯': 'The Usual Suspects',
  '银翼杀手': 'Blade Runner',
  '教父2': 'The Godfather: Part II',
  '教父3': 'The Godfather: Part III',
  '星球大战': 'Star Wars',
  '马达加斯加': 'Madagascar',
  '怪物史莱克': 'Shrek',
  '史莱克': 'Shrek',
  '加勒比海盗': 'Pirates of the Caribbean: The Curse of the Black Pearl',
  '速度与激情': 'The Fast and the Furious',
  '碟中谍': 'Mission: Impossible',
  '谍影重重': 'The Bourne Identity',
  '珍珠港': 'Pearl Harbor',
  '2012': '2012',
  '后天': 'The Day After Tomorrow',
  '小鬼当家': 'Home Alone',
  '死亡诗社': 'Dead Poets Society',
  '音乐之声': 'The Sound of Music',
  '乱世佳人': 'Gone with the Wind',
  '卡萨布兰卡': 'Casablanca',
  '公民凯恩': 'Citizen Kane',
  '十二怒汉': '12 Angry Men',
  '飞越疯人院': 'One Flew Over the Cuckoo\'s Nest',
  '闻香识女人': 'Scent of a Woman',
  '海上钢琴师': 'The Legend of 1900',
  '天堂电影院': 'Cinema Paradiso',
  '美丽心灵': 'A Beautiful Mind',
  '阿甘正传': 'Forrest Gump',
  '教父': 'The Godfather',
  '肖申克': 'The Shawshank Redemption',
  '肖申克的救赎': 'The Shawshank Redemption',
  '盗梦空间': 'Inception',
  '星际穿越': 'Interstellar',
  '千与千寻': 'Spirited Away'
};
