"""为 movierecommend_new.commentlike 生成模拟点赞数据，分布贴近现实。

现实依据（豆瓣/社区类产品普遍规律）：
- 评论点赞量呈长尾/幂律分布：多数评论 0-2 赞，少数热门评论几十至几百赞；
- 热门电影（评分人数多）的评论整体曝光更高，点赞量更大；
- 发布越早的评论曝光时间越长，点赞越多；
- 评论自身质量差异带来随机波动（对数正态噪声）。

生成模型：
- 每条评论期望点赞数 = BASE * 电影热度因子(0.5-2.5) * 时间曝光因子(0.3-2) * 对数正态噪声；
- 期望值经指数衰减映射为实际点赞数，并保证约 25-35% 评论为 0 赞；
- 点赞用户从 6040 个活跃用户中不放回抽样（同一用户对同一评论只能有一条点赞行，
  满足 uk_commentlike_user_comment 唯一约束）；
- 点赞时间 = 评论创建时间 + 对数正态延迟，封顶于数据快照时间；
- 全部 is_active=1（当前有效点赞）。

用法：
    python backend/jobs/generate_comment_likes.py --dry-run  # 仅输出分布预览
    python backend/jobs/generate_comment_likes.py            # 执行写入
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta

import numpy as np
import pymysql

DB_ARGS = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "movierecommend_new",
    "charset": "utf8mb4",
}

SNAPSHOT = datetime(2021, 12, 31)   # 数据快照时间：点赞时间不晚于该日
SEED = 42
BASE_MEAN = 4.5                     # 全站平均点赞数基准
ZERO_RATE = 0.30                    # 0 赞评论比例目标
MAX_LIKES = 600                     # 单条评论点赞上限（社区规模内合理）

INSERT_SQL = """
INSERT INTO commentlike (userid, commentid, is_active, created_at, updated_at)
VALUES (%s, %s, 1, %s, %s)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="仅输出分布预览，不写库")
    args = parser.parse_args()

    rng = random.Random(SEED)
    np.random.seed(SEED)

    conn = pymysql.connect(**DB_ARGS)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT userid FROM user WHERE status='active' AND deleted_at IS NULL"
            )
            user_ids = np.array([r[0] for r in cur.fetchall()])
            cur.execute(
                "SELECT commentid, movieid, created_at FROM moviecomment"
            )
            comments = cur.fetchall()
            # 电影热度：numrating（豆瓣段为爬虫评分人数）log 归一化到 0.5-2.5
            cur.execute(
                "SELECT movieid, COALESCE(numrating, 0) FROM movieinfo"
            )
            pop_raw = {mid: float(n or 0) for mid, n in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM commentlike")
            existing = cur.fetchone()[0]
    finally:
        conn.close()

    if existing:
        print(f"[ABORT] commentlike 已有 {existing} 行，跳过生成（避免重复）")
        return

    print(f"[DATA] 用户 {len(user_ids)} 个，评论 {len(comments)} 条")

    # 数据快照时间：最大评论时间 + 30 天，保证点赞时间始终晚于评论时间
    global SNAPSHOT
    max_created = max(c[2] for c in comments)
    SNAPSHOT = max_created + timedelta(days=30)
    print(f"[TIME] 评论时间范围: {min(c[2] for c in comments)} ~ {max_created}，"
          f"快照日 {SNAPSHOT:%Y-%m-%d}")

    # 热度因子：log1p 归一化
    vals = np.array([max(pop_raw.get(mid, 0), 0) for _, mid, _ in comments])
    logv = np.log1p(vals)
    vmax = logv.max() if logv.max() > 0 else 1.0
    pop_factor = 0.5 + 2.0 * (logv / vmax)

    # 时间曝光因子：评论发布越早，曝光越久（相对数据快照）
    created = np.array([c[2] for c in comments])
    age_days = np.array(
        [(SNAPSHOT - c[2]).days for c in comments], dtype=float
    ).clip(min=0)
    age_factor = 0.3 + 1.7 * np.log1p(age_days) / np.log1p(age_days.max())

    # 期望点赞数 + 对数正态噪声 -> 泊松强度
    noise = np.random.lognormal(mean=0.0, sigma=1.2, size=len(comments))
    lam = BASE_MEAN * pop_factor * age_factor * noise

    # 二分求解缩放系数 alpha，使泊松抽样的 0 赞占比≈ZERO_RATE
    # P(likes=0 | lam) = exp(-lam*alpha)，整体 0 赞率 = mean(exp(-lam*alpha))
    lo, hi = 1e-4, 10.0
    for _ in range(60):
        alpha = (lo + hi) / 2
        zero_frac = float(np.mean(np.exp(-lam * alpha)))
        if zero_frac > ZERO_RATE:
            lo = alpha
        else:
            hi = alpha
    alpha = (lo + hi) / 2
    likes = np.random.poisson(lam * alpha)
    likes = np.clip(likes, 0, MAX_LIKES)

    print("[DIST] 点赞数分布预览:")
    for q in (10, 25, 50, 75, 90, 95, 99):
        print(f"    P{q}: {int(np.percentile(likes, q))}")
    print(f"    max: {likes.max()}, mean: {likes.mean():.2f}, "
          f"0赞占比: {(likes == 0).mean():.1%}, 总赞数: {int(likes.sum())}")

    if args.dry_run:
        return

    # 生成点赞行
    rows = []
    for (commentid, _mid, created_at), n_like in zip(comments, likes):
        if n_like == 0:
            continue
        n_like = int(n_like)
        # 用户不放回抽样
        likers = rng.sample(list(user_ids), min(n_like, len(user_ids)))
        span_days = max((SNAPSHOT - created_at).days, 1)
        for uid in likers:
            # 点赞时间：评论发布后 1 天 ~ 快照日之间的对数正态延迟
            delay = min(
                np.random.lognormal(mean=np.log(span_days / 3.0), sigma=1.0),
                float(span_days),
            )
            like_at = created_at + timedelta(days=delay, seconds=rng.randint(0, 86399))
            dt = min(like_at, SNAPSHOT)
            rows.append((int(uid), int(commentid), dt, dt))

    rng.shuffle(rows)
    print(f"[INSERT] 待写入 {len(rows)} 行")

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
            cur.execute("SELECT COUNT(*) FROM commentlike WHERE is_active=1")
            print(f"[VERIFY] 有效点赞行数: {cur.fetchone()[0]}")
            cur.execute(
                "SELECT COUNT(DISTINCT userid), COUNT(DISTINCT commentid) FROM commentlike"
            )
            used_users, liked_comments = cur.fetchone()
            print(f"[VERIFY] 参与点赞用户: {used_users}/{len(user_ids)}；"
                  f"被点赞评论: {liked_comments}")
            cur.execute(
                "SELECT c.cnt, COUNT(*) FROM (SELECT commentid, COUNT(*) AS cnt "
                "FROM commentlike GROUP BY commentid) c GROUP BY c.cnt "
                "ORDER BY c.cnt LIMIT 15"
            )
            print("[VERIFY] 点赞数 -> 评论数 分布:")
            for cnt, n in cur.fetchall():
                print(f"    {cnt} 赞: {n} 条评论")
            cur.execute(
                "SELECT commentid, COUNT(*) AS cnt FROM commentlike "
                "GROUP BY commentid ORDER BY cnt DESC LIMIT 3"
            )
            for cid, cnt in cur.fetchall():
                print(f"[VERIFY] 最热评论 commentid={cid}: {cnt} 赞")
            cur.execute(
                "SELECT COUNT(*) FROM (SELECT userid, commentid FROM commentlike "
                "GROUP BY userid, commentid HAVING COUNT(*) > 1) t"
            )
            print(f"[VERIFY] 违反唯一约束的重复: {cur.fetchone()[0]}")
            cur.execute(
                "SELECT COUNT(*) FROM commentlike cl JOIN moviecomment mc "
                "ON mc.commentid=cl.commentid WHERE cl.created_at < mc.created_at"
            )
            print(f"[VERIFY] 点赞时间早于评论时间的行: {cur.fetchone()[0]}")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
