"""豆瓣电影 typelist 替换 + category/moviecategory 分类注入。

阶段 1：将豆瓣数据（movieid > 1000000）的中文类型替换为 MovieLens 英文类型
        （与 movieinfo 前 3000 条的类型体系一致）。
阶段 2：基于全表 typelist 拆分出类型，注入 category 表，
        并将电影与分类的关联写入 moviecategory 表。

映射方案（用户已确认）：
- 直接对应：剧情→Drama 动作→Action 喜剧→Comedy 爱情→Romance 冒险→Adventure
            奇幻→Fantasy 科幻→Sci-Fi 惊悚→Thriller 悬疑→Mystery 动画→Animation
            恐怖→Horror 犯罪→Crime 战争→War 西部→Western 纪录片→Documentary
            歌舞→Musical 儿童→Children's
- 近似映射：家庭→Children's 武侠→Action 音乐→Musical 灾难→Thriller
            传记→Drama 历史→Drama 古装→Drama 同性→Romance 运动→Drama
- 丢弃：情色、短片（无法对应且会污染分类）
- 兜底：全部类型被丢弃的电影设为 Drama，避免 typelist 为空

替换前备份豆瓣原 typelist 至 data/raw/douban/typelist_backup.csv。

用法：
    python backend/jobs/populate_categories.py            # 执行
    python backend/jobs/populate_categories.py --dry-run  # 仅预览替换结果，不写库
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

import pymysql

WORKSPACE = Path(__file__).resolve().parents[2]
BACKUP_PATH = WORKSPACE / "data" / "raw" / "douban" / "typelist_backup.csv"

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "movierecommend_new",
    "charset": "utf8mb4",
}

GENRE_MAP = {
    "剧情": "Drama",
    "动作": "Action",
    "喜剧": "Comedy",
    "爱情": "Romance",
    "冒险": "Adventure",
    "奇幻": "Fantasy",
    "科幻": "Sci-Fi",
    "惊悚": "Thriller",
    "悬疑": "Mystery",
    "动画": "Animation",
    "恐怖": "Horror",
    "犯罪": "Crime",
    "战争": "War",
    "西部": "Western",
    "纪录片": "Documentary",
    "歌舞": "Musical",
    "儿童": "Children's",
    "家庭": "Children's",
    "武侠": "Action",
    "音乐": "Musical",
    "灾难": "Thriller",
    "传记": "Drama",
    "历史": "Drama",
    "古装": "Drama",
    "同性": "Romance",
    "运动": "Drama",
    "情色": None,   # 丢弃
    "短片": None,   # 丢弃
}


def translate_typelist(raw: str) -> str:
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    translated, seen = [], set()
    for token in tokens:
        genre = GENRE_MAP.get(token, token)  # 未映射的英文 token 原样保留
        if genre and genre not in seen:
            seen.add(genre)
            translated.append(genre)
    return ",".join(translated) if translated else "Drama"


def backup_typelist(cur) -> int:
    cur.execute("SELECT movieid, typelist FROM movieinfo WHERE movieid > 1000000")
    rows = cur.fetchall()
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BACKUP_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["movieid", "typelist"])
        writer.writerows(rows)
    print(f"[BACKUP] 已备份 {len(rows)} 行原 typelist -> {BACKUP_PATH}")
    return len(rows)


def update_typelist(cur, conn, dry_run: bool) -> int:
    cur.execute("SELECT movieid, typelist FROM movieinfo WHERE movieid > 1000000")
    rows = cur.fetchall()
    updates = []
    for movieid, raw in rows:
        if not raw:
            continue
        new_value = translate_typelist(raw)
        if new_value != raw:
            updates.append((new_value, movieid))
    print(f"[UPDATE] {len(rows)} 行豆瓣数据中，{len(updates)} 行类型需要替换")
    if dry_run:
        for new_value, movieid in updates[:5]:
            print(f"[PREVIEW] movieid={movieid} -> {new_value}")
        return len(updates)
    cur.executemany("UPDATE movieinfo SET typelist = %s WHERE movieid = %s", updates)
    conn.commit()
    print(f"[DONE] 已替换 {cur.rowcount if updates else 0} 行")
    return len(updates)


def populate_categories(cur, conn) -> None:
    # 以全表 typelist 的类型 token 作为分类全集（英文体系统一）
    cur.execute("SELECT typelist FROM movieinfo WHERE typelist IS NOT NULL AND typelist <> ''")
    counter = Counter()
    for (raw,) in cur.fetchall():
        for token in {t.strip() for t in raw.split(",") if t.strip()}:
            counter[token] += 1
    genres = sorted(counter)  # 字典序，与 MovieLens 字母顺序一致
    print(f"[CATEGORY] 全表共 {len(genres)} 种类型: {', '.join(genres)}")

    # INSERT IGNORE：category.name 唯一约束，可重复执行
    cur.executemany(
        "INSERT IGNORE INTO category (name) VALUES (%s)",
        [(g,) for g in genres],
    )
    conn.commit()
    print(f"[CATEGORY] 新插入 {cur.rowcount if genres else 0} 行（已存在的自动跳过）")

    cur.execute("SELECT categoryid, name FROM category")
    name_to_id = {name: cid for cid, name in cur.fetchall()}

    cur.execute("SELECT movieid, typelist FROM movieinfo WHERE typelist IS NOT NULL AND typelist <> ''")
    associations = set()
    for movieid, raw in cur.fetchall():
        for token in {t.strip() for t in raw.split(",") if t.strip()}:
            cid = name_to_id.get(token)
            if cid:
                associations.add((movieid, cid))
    before = len(associations)
    cur.executemany(
        "INSERT IGNORE INTO moviecategory (movieid, categoryid) VALUES (%s, %s)",
        list(associations),
    )
    conn.commit()
    print(f"[MOVIECATEGORY] 关联组合 {before} 个，新插入 {cur.rowcount} 行（已存在的自动跳过）")


def verify(cur) -> None:
    cur.execute("SELECT COUNT(*) FROM category")
    print(f"[VERIFY] category 行数: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM moviecategory")
    print(f"[VERIFY] moviecategory 行数: {cur.fetchone()[0]}")
    cur.execute(
        "SELECT c.name, COUNT(mc.movieid) AS cnt FROM category c "
        "JOIN moviecategory mc ON mc.categoryid = c.categoryid "
        "GROUP BY c.name ORDER BY cnt DESC"
    )
    print("[VERIFY] 分类电影数 TOP10:")
    for name, cnt in cur.fetchall()[:10]:
        print(f"    {name}: {cnt}")
    cur.execute(
        "SELECT movieid, typelist FROM movieinfo WHERE movieid > 1000000 LIMIT 3"
    )
    for row in cur.fetchall():
        print(f"[SAMPLE] {row}")
    cur.execute(
        "SELECT COUNT(*) FROM movieinfo WHERE movieid > 1000000 "
        "AND (typelist IS NULL OR typelist = '')"
    )
    print(f"[VERIFY] 豆瓣电影 typelist 为空的行数: {cur.fetchone()[0]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="仅预览替换结果，不写数据库")
    args = parser.parse_args()

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            if args.dry_run:
                update_typelist(cur, conn, dry_run=True)
            else:
                backup_typelist(cur)
                update_typelist(cur, conn, dry_run=False)
                populate_categories(cur, conn)
                verify(cur)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
