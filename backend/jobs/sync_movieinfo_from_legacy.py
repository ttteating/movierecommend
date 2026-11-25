"""将 movierecommend.movieinfo 前 3000 条的四个字段同步到 movierecommend_new.movieinfo。

同步字段：releasetime、director、leadactors、picture。

匹配规则：
- 两库 movieinfo 均基于同一套 MovieLens ID 体系（movieid 1-3000 对应同一部电影），
  以 movieid 对齐；
- 校验片名一致：目标库片名带年份后缀（如 "Toy Story (1995)"），去掉年份后缀后
  必须与源库片名完全相同（strip 空白），否则跳过并记录，保证不会映射错电影。

用法：
    python backend/jobs/sync_movieinfo_from_legacy.py            # 执行
    python backend/jobs/sync_movieinfo_from_legacy.py --dry-run  # 仅报告差异，不写库
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata

import pymysql

DB_ARGS = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "charset": "utf8mb4",
}

UPDATE_SQL = """
UPDATE movieinfo
SET releasetime = %s, director = %s, leadactors = %s, picture = %s
WHERE movieid = %s
"""

YEAR_SUFFIX = re.compile(r"\s*\(\d{4}(?:-[^\)]*)?\)\s*$")  # 去掉 "(1995)" / "(1995-1998)" 类后缀
PARENS = re.compile(r"\([^)]*\)")  # 去掉外语名等所有括注
ARTICLES = "The|A|An|Le|La|Les|L|Un|Una|El|Los|Las|Das|Der|Die|Il"
LEADING_ARTICLE = re.compile(rf"^({ARTICLES})\s+(.+)$", re.IGNORECASE)
TRAILING_ARTICLE = re.compile(rf"^(.+?),\s*({ARTICLES})$", re.IGNORECASE)
NON_ALNUM = re.compile(r"[^a-z0-9]+")
APOSTROPHE = re.compile(r"[’']")


def norm(name: str | None) -> str:
    return (name or "").strip()


def fuzzy_title(name: str | None) -> str:
    """片名强归一化：去年份、去括注、撇号转空格、移除首尾冠词、去重音、小写、去标点。"""
    s = norm(YEAR_SUFFIX.sub("", norm(name)))
    s = PARENS.sub(" ", s)
    s = APOSTROPHE.sub(" ", s)  # L'Enfer / Enfer, L' 统一为 L Enfer / Enfer, L
    s = re.sub(r"\s+", " ", s).strip()
    m = LEADING_ARTICLE.match(s)
    if m:
        s = m.group(2)  # 直接去掉头部冠词（The X / X, The 归一为 X）
    m = TRAILING_ARTICLE.match(s)
    if m:
        s = m.group(1)  # 直接去掉尾部冠词
    # 去重音符号（é -> e）
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return NON_ALNUM.sub("", s.lower())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="仅报告差异，不写库")
    args = parser.parse_args()

    # 1. 源库：前 3000 条（movieid 1-3000）
    src = pymysql.connect(database="movierecommend", **DB_ARGS)
    try:
        with src.cursor() as cur:
            cur.execute(
                "SELECT movieid, moviename, releasetime, director, leadactors, picture "
                "FROM movieinfo ORDER BY movieid LIMIT 3000"
            )
            source = {mid: (norm(n), rel, d, a, p)
                      for mid, n, rel, d, a, p in cur.fetchall()}
    finally:
        src.close()
    print(f"[SOURCE] 源库取到 {len(source)} 行（movieid 1-3000）")

    # 2. 目标库：MovieLens 段按 movieid 对齐 + 片名校验
    dst = pymysql.connect(database="movierecommend_new", **DB_ARGS)
    try:
        with dst.cursor() as cur:
            cur.execute(
                "SELECT movieid, moviename, releasetime, director, leadactors, picture "
                "FROM movieinfo WHERE movieid <= 1000000"
            )
            targets = cur.fetchall()
            print(f"[TARGET] 目标库 MovieLens 段 {len(targets)} 行")

            updates, name_mismatch = [], []
            for mid, name, rel, d, a, p in targets:
                if mid not in source:
                    continue
                src_name, s_rel, s_d, s_a, s_p = source[mid]
                # 片名一致性校验：强归一化后必须相同（同一部电影的写法差异视为一致）
                if fuzzy_title(name) != fuzzy_title(src_name):
                    name_mismatch.append((mid, src_name, norm(name)))
                    continue
                cur_vals = (
                    rel.isoformat() if rel else None,
                    norm(d), norm(a), norm(p),
                )
                new_vals = (
                    s_rel.isoformat() if s_rel else None,
                    norm(s_d), norm(s_a), norm(s_p),
                )
                if cur_vals != new_vals:
                    updates.append((s_rel, s_d, s_a, s_p, mid))

            print(f"[MATCH] 片名校验通过: {len(targets) - len(name_mismatch)} 行；"
                  f"片名不一致跳过: {len(name_mismatch)} 行；有差异需更新: {len(updates)} 行")
            for mid, src_name, dst_name in name_mismatch[:10]:
                print(f"  [MISMATCH] movieid={mid}: 源='{src_name}' 目标='{dst_name}'")

            if args.dry_run:
                print("[DRY-RUN] 不写库")
                return
            if updates:
                cur.executemany(UPDATE_SQL, updates)
            dst.commit()
            print(f"[DONE] 已更新 {len(updates)} 行")

            # 3. 验证
            cur.execute(
                "SELECT COUNT(*) FROM movieinfo "
                "WHERE director IS NOT NULL AND director <> '' AND movieid <= 1000000"
            )
            print(f"[VERIFY] MovieLens 段有 director 的行数: {cur.fetchone()[0]}")
            cur.execute(
                "SELECT movieid, moviename, releasetime, LEFT(director, 25), "
                "LEFT(leadactors, 25), LEFT(picture, 40) "
                "FROM movieinfo WHERE movieid <= 1000000 ORDER BY movieid LIMIT 3"
            )
            for row in cur.fetchall():
                print(f"[SAMPLE] {row}")
    finally:
        dst.close()


if __name__ == "__main__":
    sys.exit(main())
