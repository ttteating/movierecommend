"""将豆瓣电影 CSV 数据集导入 movierecommend_new.movieinfo。

数据来源：Kaggle douban-movies-dataset（CC0），文件位于 data/raw/douban/。

字段映射（CSV -> movieinfo）：
- movie_id       -> movieid          （豆瓣 subject ID，int 主键，非自增，由导入提供）
- title          -> moviename
- release_date   -> releasetime      （解析失败置 NULL）
- directors      -> director
- actors         -> leadactors
- poster         -> picture
- rating         -> web_averating    （豆瓣 0-10 分制 ÷2 转为 1-5 分制，与站内 site_averating 同尺度，
                                      保证 rating_aggregation.blend_movie_rating 的融合公式口径一致）
- total_ratings  -> web_numrating
- total_ratings  -> numrating        （与 web_numrating 相同；用户确认将爬虫评分人数同时写入 numrating）
- summary        -> description      （截断至 1000 字符）
- genres         -> typelist         （截断至 255 字符）
- numrating      -> 同 web_numrating （total_ratings；缺失时置 0）
- site_averating -> NULL             （暂无站内评分明细）
- averating      -> 与 web_averating 相同（无站内评分时融合分沿用爬虫评分）

用法：
    python backend/jobs/import_douban_movieinfo.py            # 执行导入
    python backend/jobs/import_douban_movieinfo.py --dry-run  # 仅校验，不写库
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pymysql

WORKSPACE = Path(__file__).resolve().parents[2]
RAW_DIR = WORKSPACE / "data" / "raw" / "douban"

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "movierecommend_new",
    "charset": "utf8mb4",
}

# 读取顺序：all_movies 为主集合，其余为补充集合；按 movie_id 去重时保留先出现的记录
CSV_FILES = [
    "douban_all_movies.csv",
    "douban_top250_movies.csv",
    "douban_high_rating.csv",
    "douban_chinese_movies.csv",
    "douban_western_movies.csv",
    "douban_japanese_movies.csv",
    "douban_hongkong_movies.csv",
]

MAX_INT = 2**31 - 1


def load_and_merge() -> pd.DataFrame:
    frames = []
    for name in CSV_FILES:
        path = RAW_DIR / name
        if not path.exists():
            print(f"[WARN] 缺少文件，跳过: {path}")
            continue
        # utf-8-sig 自动去掉 BOM；python 引擎 + warn 跳过个别字段数损坏的行
        df = pd.read_csv(path, encoding="utf-8-sig", engine="python", on_bad_lines="warn")
        df["__source"] = name
        frames.append(df)
        print(f"[LOAD] {name}: {len(df)} 行")
    if not frames:
        raise SystemExit("没有可用的 CSV 文件")
    merged = pd.concat(frames, ignore_index=True)
    before = len(merged)
    merged = merged.drop_duplicates(subset="movie_id", keep="first")
    print(f"[MERGE] 合并 {before} 行，按 movie_id 去重后 {len(merged)} 行")
    return merged


def to_int(value) -> int | None:
    if pd.isna(value):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if 0 < number <= MAX_INT else None


def to_date(value):
    if pd.isna(value) or not str(value).strip():
        return None
    for fmt in ("%Y-%m-%d", "%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def to_rating(value) -> float | None:
    """豆瓣 0-10 分制转换为 1-5 分制。"""
    if pd.isna(value):
        return None
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None
    if not 0 <= rating <= 10:
        return None
    return round(rating / 2, 2)


def to_text(value, limit: int) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def transform(merged: pd.DataFrame) -> pd.DataFrame:
    rows = []
    stats = {"skip_no_id": 0, "skip_no_title": 0, "skip_exists": 0}
    # 已存在的 movieid（库里有 MovieLens 数据，豆瓣 ID 不应重叠，仍做防御性检查）
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT movieid FROM movieinfo")
            existing = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    for _, row in merged.iterrows():
        movie_id = to_int(row.get("movie_id"))
        if movie_id is None:
            stats["skip_no_id"] += 1
            continue
        title = to_text(row.get("title"), 1000)
        if not title:
            stats["skip_no_title"] += 1
            continue
        if movie_id in existing:
            stats["skip_exists"] += 1
            continue

        web_rating = to_rating(row.get("rating"))
        rows.append(
            {
                "movieid": movie_id,
                "moviename": title,
                "releasetime": to_date(row.get("release_date")),
                "director": to_text(row.get("directors"), 1000),
                "leadactors": to_text(row.get("actors"), 1000),
                "picture": to_text(row.get("poster"), 1000),
                "averating": round(web_rating, 1) if web_rating is not None else None,
                "numrating": to_int(row.get("total_ratings")) or 0,
                "web_averating": web_rating,
                "web_numrating": to_int(row.get("total_ratings")),
                "site_averating": None,
                "description": to_text(row.get("summary"), 1000),
                "typelist": to_text(row.get("genres"), 255),
            }
        )
    print(f"[TRANSFORM] 有效 {len(rows)} 行；跳过：无ID {stats['skip_no_id']}，"
          f"无片名 {stats['skip_no_title']}，库中已存在 {stats['skip_exists']}")
    return pd.DataFrame(rows)


INSERT_SQL = """
INSERT INTO movieinfo
  (movieid, moviename, releasetime, director, leadactors, picture,
   averating, numrating, web_averating, web_numrating, site_averating,
   description, typelist, deleted_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
"""


def load(df: pd.DataFrame, dry_run: bool) -> int:
    if df.empty:
        print("[LOAD] 无可导入数据")
        return 0
    if dry_run:
        print(f"[DRY-RUN] 将导入 {len(df)} 行，示例：")
        print(df.head(3).to_string())
        return 0
    conn = pymysql.connect(**DB_CONFIG)
    inserted = 0
    try:
        with conn.cursor() as cur:
            data = [
                (
                    r.movieid, r.moviename, r.releasetime, r.director, r.leadactors,
                    r.picture, r.averating, r.numrating, r.web_averating,
                    r.web_numrating, r.site_averating, r.description, r.typelist,
                )
                for r in df.itertuples(index=False)
            ]
            inserted = cur.executemany(INSERT_SQL, data)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="仅校验转换结果，不写数据库")
    args = parser.parse_args()

    merged = load_and_merge()
    df = transform(merged)
    if args.dry_run:
        load(df, dry_run=True)
    else:
        inserted = load(df, dry_run=False)
        print(f"[DONE] 实际插入 {inserted} 行到 {DB_CONFIG['database']}.movieinfo")

    # 导入后验证
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM movieinfo")
            print(f"[VERIFY] movieinfo 总行数: {cur.fetchone()[0]}")
            cur.execute("SELECT COUNT(*) FROM movieinfo WHERE web_averating IS NOT NULL")
            print(f"[VERIFY] 含豆瓣评分(web_averating)的行数: {cur.fetchone()[0]}")
            cur.execute(
                "SELECT movieid, moviename, releasetime, averating, web_averating, "
                "web_numrating, numrating FROM movieinfo ORDER BY movieid DESC LIMIT 3"
            )
            for row in cur.fetchall():
                print(f"[SAMPLE] {row}")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
