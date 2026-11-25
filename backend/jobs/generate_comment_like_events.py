"""为 movierecommend_new.commentlike_event 生成与 commentlike 一致的点赞操作历史。

一致性规则：
- commentlike 中每条 is_active=1 的点赞行，其事件历史的最后一条必须是 'like'，
  且事件时间等于 commentlike.created_at；
- 部分点赞行（默认 10%）模拟真实用户的反复切换：在最终点赞之前插入
  1 次或多次 "like -> unlike" 循环（时间严格递增，且都不晚于最终点赞时间，
  不早于评论创建时间）；
- 最终事件为 unlike 的用户在 commentlike 中对应 is_active=0 的行，
  本库未生成这类行，因此不产生尾部 unlike 事件。

用法：
    python backend/jobs/generate_comment_like_events.py --dry-run  # 仅统计预览
    python backend/jobs/generate_comment_like_events.py            # 执行写入
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import timedelta

import pymysql

DB_ARGS = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "movierecommend_new",
    "charset": "utf8mb4",
}

SEED = 42
TOGGLE_RATE = 0.10          # 模拟切换行为的点赞行比例
MAX_EXTRA_CYCLES = 2        # 单行最多额外 like->unlike 循环次数
MIN_SPAN_DAYS = 3           # 评论时间与点赞时间跨度小于该值时不插入切换历史

INSERT_SQL = """
INSERT INTO commentlike_event (userid, commentid, action, created_at)
VALUES (%s, %s, %s, %s)
"""


def rand_time(rng: random.Random, start, end):
    """[start, end) 内随机时刻；end > start 保证可用。"""
    span = int((end - start).total_seconds())
    if span <= 0:
        return None
    return start + timedelta(seconds=rng.randint(0, span - 1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="仅统计预览，不写库")
    args = parser.parse_args()

    rng = random.Random(SEED)

    conn = pymysql.connect(**DB_ARGS)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM commentlike_event")
            existing = cur.fetchone()[0]
            if existing:
                print(f"[ABORT] commentlike_event 已有 {existing} 行，跳过")
                return
            # 点赞行 + 对应评论创建时间
            cur.execute(
                "SELECT cl.userid, cl.commentid, cl.created_at, mc.created_at "
                "FROM commentlike cl JOIN moviecomment mc ON mc.commentid = cl.commentid "
                "WHERE cl.is_active = 1"
            )
            likes = cur.fetchall()
    finally:
        conn.close()

    print(f"[DATA] 有效点赞行 {len(likes)} 条")

    rows = []
    toggled = 0
    for userid, commentid, like_at, comment_at in likes:
        span_days = (like_at - comment_at).total_seconds() / 86400
        # 插入切换历史：like -> unlike 循环，时间严格递增
        if span_days >= MIN_SPAN_DAYS and rng.random() < TOGGLE_RATE:
            cycles = rng.randint(1, MAX_EXTRA_CYCLES)
            # 将 [comment_at, like_at] 分成 cycles 段，每段内放 like/unlike
            segment = (like_at - comment_at) / (cycles + 1)
            for c in range(cycles):
                seg_start = comment_at + segment * c
                seg_end = comment_at + segment * (c + 1)
                t_like = rand_time(rng, seg_start, seg_end)
                t_unlike = rand_time(rng, t_like, seg_end) if t_like else None
                if t_like and t_unlike:
                    rows.append((userid, commentid, "like", t_like))
                    rows.append((userid, commentid, "unlike", t_unlike))
                    toggled += 1
        # 最终 like 事件：与 commentlike.created_at 完全一致
        rows.append((userid, commentid, "like", like_at))

    rows.sort(key=lambda r: r[3])
    print(f"[EVENTS] 共 {len(rows)} 条事件（切换历史 {toggled} 组，"
          f"最终 like {len(likes)} 条）")
    like_cnt = sum(1 for r in rows if r[2] == "like")
    unlike_cnt = len(rows) - like_cnt
    print(f"[EVENTS] like {like_cnt} 条 / unlike {unlike_cnt} 条")

    if args.dry_run:
        print("[DRY-RUN] 不写库")
        return

    conn = pymysql.connect(**DB_ARGS)
    inserted = 0
    try:
        with conn.cursor() as cur:
            for i in range(0, len(rows), 10000):
                inserted += cur.executemany(INSERT_SQL, rows[i:i + 10000])
        conn.commit()
        print(f"[DONE] 实际写入 {inserted} 行")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # 验证
    conn = pymysql.connect(**DB_ARGS)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM commentlike_event")
            print(f"[VERIFY] commentlike_event 总行数: {cur.fetchone()[0]}")
            cur.execute(
                "SELECT COUNT(*) FROM commentlike cl WHERE NOT EXISTS ("
                "SELECT 1 FROM commentlike_event e WHERE e.userid=cl.userid "
                "AND e.commentid=cl.commentid)"
            )
            print(f"[VERIFY] 无事件历史的有效点赞行: {cur.fetchone()[0]}")
            cur.execute(
                "SELECT COUNT(*) FROM (SELECT userid, commentid "
                "FROM commentlike_event GROUP BY userid, commentid "
                "HAVING SUBSTRING_INDEX(GROUP_CONCAT(action ORDER BY created_at), ',', -1) <> 'like') t"
            )
            print(f"[VERIFY] 最后事件不是 like 的用户评论对: {cur.fetchone()[0]}")
            cur.execute(
                "SELECT COUNT(*) FROM commentlike_event e JOIN moviecomment mc "
                "ON mc.commentid=e.commentid WHERE e.created_at < mc.created_at"
            )
            print(f"[VERIFY] 事件时间早于评论时间的行: {cur.fetchone()[0]}")
            cur.execute(
                "SELECT COUNT(*) FROM (SELECT userid, commentid, action, created_at "
                "FROM commentlike_event GROUP BY userid, commentid, action, created_at "
                "HAVING COUNT(*) > 1) t"
            )
            print(f"[VERIFY] 完全重复的事件行: {cur.fetchone()[0]}")
            cur.execute("SELECT action, COUNT(*) FROM commentlike_event GROUP BY action")
            for action, cnt in cur.fetchall():
                print(f"[VERIFY] {action}: {cnt} 条")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
