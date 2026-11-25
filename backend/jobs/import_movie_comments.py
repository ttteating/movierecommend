"""将豆瓣影评数据集注入 movierecommend_new.moviecomment。

数据源：Douban-Movie-Review-Dataset-master（data/*/origin、data_new/*/origin、data_all），
仅取与 movieinfo 已匹配的 281 部电影（清单：data/raw/douban/review_dataset_matched_movies.csv）。

核心规则（用户已确认）：
- moviecomment.userid 映射到 user 表已有的 6040 个活跃用户（userid 34297-40336），
  不为豆瓣用户名创建新账号；
- 尽量让每个用户都有评论：每部电影内用户不重复，注入后对 0 评论用户
  从多评论用户处回收再分配，保证全覆盖；
- time 为北京时间，减 8 小时转换为 UTC 后写入 created_at；
- content 截断至 500 字符（varchar(500)）；moderation_status=published；
- 同一部电影内按 (uname, time, comment) 去重；同一电影源文件有多个版本时
  取有效行数最多的一个（origin/sorted/data_all 不混用，避免重复评论）。

用法：
    python backend/jobs/import_movie_comments.py            # 执行
    python backend/jobs/import_movie_comments.py --dry-run  # 仅统计，不写库
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pymysql

WORKSPACE = Path(__file__).resolve().parents[2]
MATCHED_CSV = WORKSPACE / "data" / "raw" / "douban" / "review_dataset_matched_movies.csv"
DATASET_ROOT = Path(r"C:\Users\Eattin\Downloads\Douban-Movie-Review-Dataset-master"
                    r"\Douban-Movie-Review-Dataset-master")

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "movierecommend_new",
    "charset": "utf8mb4",
}

CONTENT_LIMIT = 500
BEIJING_OFFSET = timedelta(hours=8)  # 北京时间 UTC+8

INSERT_SQL = """
INSERT INTO moviecomment (userid, movieid, content, moderation_status, created_at)
VALUES (%s, %s, %s, 'published', %s)
"""


def norm_name(s: str) -> str:
    s = re.sub(r"^douban_movie_xsk_\d+-\d+", "", s)
    s = re.sub(r"sorted$", "", s)
    return re.sub(r"\s+", "", s).strip()


COLUMNS = ["time", "uname", "comment", "star", "title", "support", "sentiment_score"]


def build_file_index() -> dict[str, list[Path]]:
    """数据集内全部影评 CSV 按规范化电影名建索引（origin / sorted / data_all）。"""
    index: dict[str, list[Path]] = {}
    for path in DATASET_ROOT.rglob("*.csv"):
        p = str(path).replace("\\", "/")
        if not ("/origin/" in p or "/sorted/" in p or "data_all" in p):
            continue  # result/ 是星级统计聚合表，不含逐条评论，跳过
        key = norm_name(path.stem)
        if key:
            index.setdefault(key, []).append(path)
    return index


def parse_file(path: Path) -> pd.DataFrame:
    # 动态判断表头：首行以日期开头（如 2005-07-08 ...）则无表头（sorted/、部分 data_all 文件）
    with open(path, encoding="utf-8", errors="replace") as fh:
        first_line = fh.readline(4096)
    is_headerless = bool(re.match(r"\s*\"?\s*\d{4}-\d{2}-\d{2}", first_line))
    try:
        df = pd.read_csv(
            path,
            engine="python",
            on_bad_lines="skip",
            header=None if is_headerless else "infer",
            names=COLUMNS if is_headerless else None,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARN] 解析失败 {path.name}: {exc}")
        return pd.DataFrame()
    if not {"time", "uname", "comment"}.issubset(df.columns):
        return pd.DataFrame()
    for col in ("time", "uname", "comment"):
        df[col] = df[col].astype(str).str.strip()
    df["time"] = pd.to_datetime(
        df["time"].str.replace('"', "", regex=False).str.strip(),
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )
    df = df.dropna(subset=["time"])
    df = df[(df["comment"] != "") & (df["comment"].str.lower() != "nan")]
    df["comment"] = df["comment"].str[:CONTENT_LIMIT]
    df = df.drop_duplicates(subset=["uname", "time", "comment"])
    return df


def load_comments(file_index: dict[str, list[Path]]) -> pd.DataFrame:
    matched = pd.read_csv(MATCHED_CSV, encoding="utf-8-sig")
    frames = []
    for _, row in matched.iterrows():
        movie_id = int(row["movieid"])
        key = norm_name(str(row["dataset_filename"]))
        candidates = file_index.get(key, [])
        if not candidates:
            print(f"  [MISS] 未找到影评文件: {row['dataset_filename']}")
            continue
        best, best_df = None, pd.DataFrame()
        for path in candidates:
            parsed = parse_file(path)
            if len(parsed) > len(best_df):
                best, best_df = path, parsed
        if best_df.empty:
            continue
        best_df = best_df.copy()
        best_df["movieid"] = movie_id
        best_df["__src"] = str(best)
        frames.append(best_df[["movieid", "uname", "comment", "time", "__src"]])
    all_df = pd.concat(frames, ignore_index=True)
    # 北京时间 -> UTC
    all_df["created_at"] = all_df["time"] - BEIJING_OFFSET
    print(f"[COMMENTS] 共解析 {len(all_df)} 条评论，覆盖 {all_df['movieid'].nunique()} 部电影")
    return all_df


def assign_users(all_df: pd.DataFrame, user_ids: list[int]) -> pd.DataFrame:
    rng = random.Random(42)
    users = list(user_ids)
    rng.shuffle(users)
    assigned = []
    for movie_id, group in all_df.groupby("movieid", sort=False):
        rows = group.index.tolist()
        if len(rows) <= len(users):
            chosen = rng.sample(users, len(rows))  # 同一电影内用户不重复
        else:
            chosen = rng.choices(users, k=len(rows))
        assigned.extend(zip(rows, chosen))
    all_df = all_df.copy()
    for idx, uid in assigned:
        all_df.at[idx, "userid"] = uid
    all_df["userid"] = all_df["userid"].astype(int)

    # 覆盖保障：0 评论用户从评论数 >= 2 的用户处回收一条评论再分配
    counts = all_df["userid"].value_counts()
    zero_users = [u for u in users if counts.get(u, 0) == 0]
    donor_pool = all_df.index[all_df["userid"].map(counts) >= 2].tolist()
    rng.shuffle(donor_pool)
    fixed = 0
    for uid in zero_users:
        if not donor_pool:
            break
        donor_idx = donor_pool.pop()
        donor_uid = all_df.at[donor_idx, "userid"]
        if counts.get(donor_uid, 0) < 2:
            donor_pool.append(donor_idx)
            continue
        all_df.at[donor_idx, "userid"] = uid
        counts[donor_uid] -= 1
        counts[uid] = 1
        fixed += 1
    print(f"[USERS] 使用 {all_df['userid'].nunique()}/{len(users)} 个用户；"
          f"0 评论用户回收再分配 {fixed} 条")
    return all_df


def insert_comments(all_df: pd.DataFrame) -> int:
    conn = pymysql.connect(**DB_CONFIG)
    inserted = 0
    try:
        with conn.cursor() as cur:
            data = [
                (int(r.userid), int(r.movieid), r.comment, r.created_at.to_pydatetime())
                for r in all_df.itertuples(index=False)
            ]
            for i in range(0, len(data), 5000):
                batch = data[i:i + 5000]
                inserted += cur.executemany(INSERT_SQL, batch)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return inserted


def verify() -> None:
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM moviecomment")
            total = cur.fetchone()[0]
            print(f"[VERIFY] moviecomment 总行数: {total}")
            cur.execute(
                "SELECT COUNT(DISTINCT userid), "
                "(SELECT COUNT(*) FROM user WHERE status='active' AND deleted_at IS NULL) "
                "FROM moviecomment"
            )
            used, total_users = cur.fetchone()
            print(f"[VERIFY] 有评论的用户: {used}/{total_users}")
            cur.execute(
                "SELECT COUNT(*) FROM user u WHERE u.status='active' AND u.deleted_at IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM moviecomment mc WHERE mc.userid=u.userid)"
            )
            print(f"[VERIFY] 仍无评论的活跃用户: {cur.fetchone()[0]}")
            cur.execute(
                "SELECT mc.movieid, m.moviename, COUNT(*) FROM moviecomment mc "
                "JOIN movieinfo m ON m.movieid=mc.movieid "
                "GROUP BY mc.movieid, m.moviename ORDER BY COUNT(*) DESC LIMIT 5"
            )
            for mid, name, cnt in cur.fetchall():
                print(f"[VERIFY] {name} (movieid={mid}): {cnt} 条评论")
            cur.execute(
                "SELECT userid, movieid, LEFT(content, 30), created_at "
                "FROM moviecomment ORDER BY commentid LIMIT 3"
            )
            for row in cur.fetchall():
                print(f"[SAMPLE] {row}")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写数据库")
    args = parser.parse_args()

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT userid FROM user WHERE status='active' AND deleted_at IS NULL"
            )
            user_ids = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    print(f"[USERS] 活跃用户 {len(user_ids)} 个")

    file_index = build_file_index()
    print(f"[INDEX] 影评源文件 {sum(len(v) for v in file_index.values())} 个，"
          f"唯一电影 {len(file_index)} 部")
    all_df = load_comments(file_index)
    all_df = assign_users(all_df, user_ids)

    if args.dry_run:
        print("[DRY-RUN] 每部电影评论数分布:")
        print(all_df.groupby("movieid").size().describe().to_string())
        return
    inserted = insert_comments(all_df)
    print(f"[DONE] 实际插入 {inserted} 条评论")
    verify()


if __name__ == "__main__":
    sys.exit(main())
