#!/usr/bin/env python3
"""Seed the schema in the CURRENT dump. No DDL; one atomic DML transaction.

Default: read-only plan. --execute writes, --mode rebuild deletes ALL target rows.
See docs/mock-data.md. Python 3.10+, requirements in database/seed/requirements.txt.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import random
import re
import secrets
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
TABLES = ('user', 'personalratings', 'userfavorite', 'moviecomment',
          'commentlike', 'commentlike_event', 'recommendationitem',
          'recommendationevent', 'recommendresult')
DELETE_ORDER = ('recommendationevent', 'recommendationitem', 'recommendresult',
                'commentlike_event', 'commentlike', 'moviecomment',
                'userfavorite', 'personalratings', 'user')
LOG = logging.getLogger('mock-data')


def ident(name):
    return '`' + name.replace('`', '``') + '`'


def args_parse():
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true', help='Otherwise read-only plan')
    p.add_argument('--rollback-test', action='store_true', help='Exercise inserts/validation then ROLLBACK; requires --execute')
    p.add_argument('--mode', choices=['append', 'rebuild'], default='append')
    p.add_argument('--offline', action='store_true', help='Plan only; requires MOVIE_COUNT')
    p.add_argument('--dump', type=Path, default=ROOT / 'database/dumps/movierecommend.sql')
    p.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    p.add_argument('--host', default=os.getenv('MYSQL_HOST'))
    p.add_argument('--port', type=int, default=int(os.environ['MYSQL_PORT']) if os.getenv('MYSQL_PORT') else None)
    p.add_argument('--user', default=os.getenv('MYSQL_USER'))
    p.add_argument('--password', default=os.getenv('MYSQL_PASSWORD'))
    p.add_argument('--database', default=os.getenv('MYSQL_DATABASE'))
    p.add_argument('--ssl-ca', default=os.getenv('MYSQL_SSL_CA'))
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--batch-size', type=int, default=1000)
    p.add_argument('--movie-count', type=int, default=int(os.getenv('MOVIE_COUNT', '0')),
                   help='Sizing baseline only; never invents movie IDs')
    p.add_argument('--movie-ratio', type=float, default=1.0, help='Fraction of active movies sampled')
    p.add_argument('--users-per-movie', type=float, default=.1)
    p.add_argument('--ratings-per-user', type=int, default=40)
    p.add_argument('--comments-per-user', type=int, default=4)
    p.add_argument('--favorites-per-user', type=int, default=10)
    p.add_argument('--likes-per-comment', type=int, default=3)
    p.add_argument('--unlike-rate', type=float, default=.2)
    p.add_argument('--relike-rate', type=float, default=.1, help='Conditional on unlike')
    p.add_argument('--requests-per-user', type=int, default=3)
    p.add_argument('--items-per-request', type=int, default=10)
    p.add_argument('--impression-rate', type=float, default=.8)
    p.add_argument('--click-rate', type=float, default=.15, help='Conditional on impression')
    p.add_argument('--not-interested-rate', type=float, default=.05,
                   help='Conditional on impression; mutually exclusive with click')
    p.add_argument('--history-days', type=int, default=180)
    p.add_argument('--as-of', help='UTC ISO time; fixed value makes logical data repeatable')
    p.add_argument('--run-tag', default=secrets.token_hex(6), help='1-12 lowercase hex digits')
    p.add_argument('--password-hash', default=os.getenv('SEED_PASSWORD_HASH'),
                   help='Existing bcrypt hash; no plaintext is written or logged')
    a = p.parse_args()
    if not re.fullmatch('[0-9a-f]{1,12}', a.run_tag):
        p.error('run-tag must contain 1-12 lowercase hex digits')
    for n in ('batch_size', 'history_days', 'ratings_per_user', 'comments_per_user',
              'favorites_per_user', 'likes_per_comment', 'requests_per_user', 'items_per_request'):
        if getattr(a, n) <= 0:
            p.error(n + ' must be positive')
    if a.movie_count < 0 or not math.isfinite(a.users_per_movie) or a.users_per_movie <= 0:
        p.error('movie-count >= 0 and users-per-movie > 0 required')
    for n in ('movie_ratio', 'unlike_rate', 'relike_rate', 'impression_rate',
              'click_rate', 'not_interested_rate'):
        if not 0 <= getattr(a, n) <= 1:
            p.error(n + ' must be between 0 and 1')
    if a.movie_ratio == 0 or a.click_rate + a.not_interested_rate > 1:
        p.error('movie-ratio > 0 and click-rate + not-interested-rate <= 1 required')
    if a.offline and (a.execute or not a.movie_count):
        p.error('offline requires --movie-count and does not allow --execute')
    if a.rollback_test and not a.execute:
        p.error('--rollback-test requires --execute')
    supplied_time = datetime.fromisoformat(a.as_of.replace('Z', '+00:00')) if a.as_of else datetime.now(timezone.utc)
    if supplied_time.tzinfo is None:
        supplied_time = supplied_time.replace(tzinfo=timezone.utc)
    a.as_of = supplied_time.astimezone(timezone.utc).replace(tzinfo=None)
    if a.as_of < datetime(1970, 1, 1) + timedelta(days=a.history_days):
        p.error('history must be after Unix epoch')
    return a


def canonical(expression):
    # MySQL SHOW CREATE and Navicat use different whitespace/parentheses/charset introducers.
    s = re.sub(r"_utf8(?:mb[34])?(?=')", '', expression.lower())
    return re.sub(r'[\s`()]+', '', s)


def signature(ddl):
    """Compare columns/defaults/generated expressions, PK/UQ, FKs and CHECKs to dump."""
    cols, keys, fks, checks = {}, [], [], []
    table_collation = re.search(r'\)\s*ENGINE\s*=.*?\bCOLLATE\s*=\s*(\w+)', ddl, re.I)
    charset = re.search(r'\bCHARSET\s*=\s*(\w+)', ddl, re.I)
    inherited_collation = table_collation[1].lower() if table_collation else (
        {'utf8mb3': 'utf8mb3_general_ci', 'utf8mb4': 'utf8mb4_0900_ai_ci'}.get(charset[1].lower()) if charset else None)
    for line in ddl.splitlines()[1:]:
        line = line.strip().rstrip(',')
        m = re.match(r'`([^`]+)`\s+([a-z]+(?:\([\d, ]+\))?)(.*)', line, re.I)
        if m:
            name, typ, tail = m.groups()
            default = re.search(r"\bDEFAULT\s+('(?:[^']|'')*'|CURRENT_TIMESTAMP(?:\(\d+\))?|NULL|[-\d.]+)", tail, re.I)
            generated = re.search(r'GENERATED ALWAYS AS\s*\((.*)\)\s*(?:STORED|VIRTUAL)', tail, re.I)
            collation = re.search(r'COLLATE\s+(\w+)', tail, re.I)
            cols[name] = (canonical(typ), 'NOT NULL' in tail.upper(),
                          (canonical(default[1]).strip("'") if typ.lower().startswith(('int', 'bigint', 'tinyint', 'decimal', 'double', 'float'))
                           else canonical(default[1])) if default else None,
                          'AUTO_INCREMENT' in tail.upper(),
                          canonical(generated[1]) if generated else None,
                          collation[1].lower() if collation else
                          (inherited_collation if typ.lower().startswith(('varchar', 'char', 'text')) else None),
                          'ON UPDATE' in tail.upper())
        elif re.match(r'(PRIMARY KEY|UNIQUE (?:INDEX|KEY))', line, re.I):
            keys.append(('PK' if line.upper().startswith('PRIMARY') else 'UQ',
                         tuple(re.findall(r'`([^`]+)`', line[line.index('('):]))))
        elif 'FOREIGN KEY' in line.upper():
            actions = []
            for operation in ('DELETE', 'UPDATE'):
                action = re.search(r'ON ' + operation + r' (RESTRICT|CASCADE|SET NULL|NO ACTION)', line, re.I)
                actions.append(action[1].upper() if action else 'RESTRICT')
            fks.append((*re.findall(r'`([^`]+)`', line)[1:], *actions))
        elif ' CHECK ' in line.upper():
            checks.append(canonical(line.split('CHECK', 1)[1]))
    return cols, sorted(keys), sorted(fks), sorted(checks)


def load_schema(path):
    text = path.read_text(encoding='utf-8-sig')
    ddl = dict(re.findall(r'CREATE TABLE `([^`]+)`\s*(\(.*?\) ENGINE[^;]*);', text, re.S))
    return {t: 'CREATE TABLE ' + ident(t) + ' ' + ddl[t]
            for t in (*TABLES, 'movieinfo')}


def connect(a):
    import pymysql
    u = urlsplit(a.database_url or '')
    config = dict(host=a.host or u.hostname or '127.0.0.1',
                  port=a.port or u.port or 3306,
                  user=a.user or unquote(u.username or ''),
                  password=a.password if a.password is not None else unquote(u.password or ''),
                  database=a.database or unquote(u.path.lstrip('/')),
                  charset='utf8mb4', autocommit=False, connect_timeout=10,
                  read_timeout=120, write_timeout=120)
    if a.ssl_ca:
        config['ssl'] = {'ca': a.ssl_ca, 'check_hostname': True}
    if not config['user'] or not config['database']:
        raise ValueError('Configure DATABASE_URL or MYSQL_USER/MYSQL_DATABASE')
    return pymysql.connect(**config)


def preflight(q, schema):
    q.execute("SET time_zone = '+00:00'")
    q.execute("SET SESSION sql_mode = 'STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'")
    q.execute('SELECT @@foreign_key_checks')
    if q.fetchone() != (1,):
        raise ValueError('Foreign key enforcement must already be enabled')
    q.execute("SELECT TABLE_NAME FROM information_schema.TABLE_CONSTRAINTS "
              "WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_TYPE='CHECK' AND ENFORCED<>'YES'")
    if any(row[0] in schema for row in q.fetchall()):
        raise ValueError('CHECK constraints must be enforced')
    for t, ddl in schema.items():
        q.execute('SHOW CREATE TABLE ' + ident(t))
        live = q.fetchone()[1]
        if not re.search(r'ENGINE=InnoDB', live, re.I) or signature(live) != signature(ddl):
            raise ValueError('Schema differs from current dump: ' + t)
    LOG.info('Schema verified against latest dump; no DDL will be executed')


def plan(a, available):
    pool = max(1, math.ceil(available * a.movie_ratio))
    baseline = a.movie_count or available
    users = max(1, math.ceil(baseline * a.movie_ratio * a.users_per_movie))
    ratings = min(a.ratings_per_user, pool)
    comments = min(a.comments_per_user, ratings)
    favorites = min(a.favorites_per_user, pool)
    likes = min(a.likes_per_comment, users - 1)
    items = min(a.items_per_request, pool)
    counts = dict(user=users, personalratings=users * ratings,
                  moviecomment=users * comments, userfavorite=users * favorites,
                  commentlike=users * comments * likes,
                  recommendationitem=users * a.requests_per_user * items,
                  recommendresult=users * items)
    counts['commentlike_event'] = counts['commentlike'] * (1 + a.unlike_rate * (1 + a.relike_rate))
    counts['recommendationevent'] = counts['recommendationitem'] * a.impression_rate * (
        1 + a.click_rate + a.not_interested_rate)
    LOG.info('Movie rows=%s; baseline=%s; sampled pool=%s; estimated counts=%s',
             available, baseline, pool, json.dumps(counts))
    return users, pool, ratings, comments, favorites, likes, items


class Writer:
    def __init__(self, q, batch):
        self.q, self.batch = q, batch
        self.pending, self.counts = {}, Counter()

    def add(self, table, columns, row):
        key = (table, columns)
        self.pending.setdefault(key, []).append(row)
        if len(self.pending[key]) >= self.batch:
            self.flush(key)

    def flush(self, key=None):
        for k in ([key] if key else list(self.pending)):
            rows = self.pending[k]
            if not rows:
                continue
            table, columns = k
            sql = 'INSERT INTO ' + ident(table) + ' (' + ','.join(map(ident, columns.split()))
            sql += ') VALUES (' + ','.join(['%s'] * len(rows[0])) + ')'
            self.q.executemany(sql, rows)
            self.counts[table] += len(rows)
            rows.clear()
            LOG.info('Inserted %s total=%s (not committed)', table, self.counts[table])


def generate(a, q, movies, shape):
    import bcrypt
    if not a.password_hash or not re.fullmatch(r'\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}', a.password_hash):
        raise ValueError('Set SEED_PASSWORD_HASH to a bcrypt hash matching the application')
    bcrypt.checkpw(b'seed-format-check', a.password_hash.encode('ascii'))
    rng = random.Random(a.seed)
    n, pool, nr, nc, nf, nl, ni = shape
    if n > 999999:
        raise ValueError('At most 999999 users per run-tag')
    movies = rng.sample(movies, pool)
    by_movie = {m[0]: m for m in movies}
    mids = sorted(by_movie)
    prefix = 'sim' + a.run_tag + '_'
    pattern = prefix.replace('_', '\\_') + '%'
    q.execute('SELECT COUNT(*) FROM `user` WHERE username LIKE %s', (pattern,))
    if q.fetchone()[0]:
        raise ValueError('run-tag already exists; choose a new tag for append')
    w = Writer(q, a.batch_size)
    start = a.as_of - timedelta(days=a.history_days)

    def moment(lo, hi):
        return lo + (hi - lo) * rng.random()

    registrations = {}
    for i in range(n):
        name = prefix + f'{i:06d}'
        created = moment(start, start + (a.as_of - start) * .2)
        registrations[name] = created
        # Synthetic identifiers, not deliverable telephone/email contacts.
        w.add('user', 'username password phone email status created_at updated_at',
              (name, a.password_hash, 'sim' + a.run_tag + f'{i:06d}',
               name + '@example.invalid', 'active', created, created))
    w.flush()
    q.execute('SELECT userid,username FROM `user` WHERE username LIKE %s ORDER BY username', (pattern,))
    users = [(uid, registrations[name]) for uid, name in q.fetchall()]
    if len(users) != n:
        raise ValueError('Unexpected number of new users')
    # IDs are read back; no MAX(id)+1 or assumptions about auto-increment stride/gaps.
    for user_index, (uid, registered) in enumerate(users):
        rated = rng.sample(mids, nr)
        rating_times = {}
        for mid in rated:
            t = moment(registered, a.as_of - timedelta(hours=2))
            rating_times[mid] = t
            unix = str(int(t.replace(tzinfo=timezone.utc).timestamp()))
            if len(unix) > 10:
                raise ValueError('Unix timestamp does not fit char(10)')
            w.add('personalratings', 'userid movieid rating timestamp rated_at',
                  (uid, mid, rng.randint(1, 10), unix, t))
        for mid in rng.sample(rated, nc):
            t = moment(rating_times[mid], a.as_of - timedelta(hours=1))
            content = rng.choice(('叙事节奏清晰，值得再看。', '表演自然，配乐令人印象深刻。',
                                  '题材有趣，结尾还有回味。', '画面表现出色，剧情略显平淡。'))
            w.add('moviecomment', 'userid movieid content moderation_status created_at',
                  (uid, mid, content, 'published', t))
        for mid in rng.sample(mids, nf):
            t = moment(registered, a.as_of)
            status = 'watched' if mid in rating_times else 'want_to_watch'
            if mid in rating_times:
                t = max(t, rating_times[mid])
            w.add('userfavorite', 'userid movieid status created_at updated_at',
                  (uid, mid, status, t, t))
        generated_times = sorted(moment(registered, a.as_of - timedelta(minutes=5))
                                 for _ in range(a.requests_per_user))
        for j, generated in enumerate(generated_times):
            request = prefix + f'{user_index:06d}_{j:010d}'
            if len(request) > 64:
                raise ValueError('request_id exceeds varchar(64)')
            for position, mid in enumerate(rng.sample(mids, ni), 1):
                _, title, rating = by_movie[mid]
                snapshot = None if rating is None else Decimal(str(rating)).quantize(Decimal('.1'))
                if snapshot is not None and not Decimal('-999.9') <= snapshot <= Decimal('999.9'):
                    raise ValueError('Movie rating cannot fit recommendation snapshot: ' + str(mid))
                w.add('recommendationitem', 'request_id userid movieid position movie_rating_snapshot generated_at',
                      (request, uid, mid, position, snapshot, generated))
                # Legacy table contains ONLY the final simulated request for each new user.
                if j == a.requests_per_user - 1:
                    w.add('recommendresult', 'userid movieid rating moviename', (uid, mid, rating, title))
    w.flush()
    q.execute('SELECT c.commentid,c.userid,c.created_at FROM moviecomment c '
              'JOIN `user` u ON u.userid=c.userid WHERE u.username LIKE %s ORDER BY c.commentid', (pattern,))
    comments = q.fetchall()
    uid_order = {uid: i for i, (uid, _) in enumerate(users)}
    for cid, author, created in comments:
        # Sample indexes from n-1 without building a full user list for each comment.
        excluded = uid_order[author]
        for index in rng.sample(range(n - 1), nl):
            index += index >= excluded
            uid, registered = users[index]
            first = moment(max(created, registered), a.as_of - timedelta(seconds=3))
            history = [('like', first)]
            if rng.random() < a.unlike_rate:
                history.append(('unlike', moment(first + timedelta(microseconds=1), a.as_of - timedelta(seconds=1))))
                if rng.random() < a.relike_rate:
                    history.append(('like', moment(history[-1][1] + timedelta(microseconds=1), a.as_of)))
            active = int(history[-1][0] == 'like')
            w.add('commentlike', 'userid commentid is_active created_at updated_at',
                  (uid, cid, active, first, history[-1][1]))
            for action, t in history:
                w.add('commentlike_event', 'userid commentid action created_at', (uid, cid, action, t))
    w.flush()
    q.execute('SELECT i.recommendationid,i.generated_at FROM recommendationitem i '
              'JOIN `user` u ON u.userid=i.userid WHERE u.username LIKE %s ORDER BY i.recommendationid', (pattern,))
    for rid, generated in q.fetchall():
        if rng.random() < a.impression_rate:
            exposed = generated + timedelta(seconds=rng.randint(1, 60))
            w.add('recommendationevent', 'recommendationid event_type created_at', (rid, 'impression', exposed))
            draw = rng.random()
            event = ('click' if draw < a.click_rate else 'not_interested'
                     if draw < a.click_rate + a.not_interested_rate else None)
            if event:
                w.add('recommendationevent', 'recommendationid event_type created_at',
                      (rid, event, exposed + timedelta(seconds=rng.randint(1, 180))))
    w.flush()
    return w.counts


def validate(q, schema):
    """Generic physical constraints, plus semantic checks from validate_mock_data.sql."""
    def check(label, sql):
        q.execute(sql)
        count = q.fetchone()[0]
        LOG.info('Validation %s: %s violations', label, count)
        if count:
            raise ValueError('Validation failed: ' + label)

    for t in TABLES:
        columns, keys, fks, checks = signature(schema[t])
        required = [ident(c) + ' IS NULL' for c, meta in columns.items() if meta[1]]
        if required:
            check(t + ' NOT NULL', 'SELECT COUNT(*) FROM ' + ident(t) + ' WHERE ' + ' OR '.join(required))
        for _, key in keys:
            group = ','.join(map(ident, key))
            present = ' AND '.join(ident(k) + ' IS NOT NULL' for k in key)
            check(t + ' unique ' + group, f'SELECT COUNT(*) FROM (SELECT {group} FROM {ident(t)} '
                  f'WHERE {present} GROUP BY {group} HAVING COUNT(*)>1) d')
        for child, parent, parent_col, _, _ in fks:
            check(t + ' FK ' + child, 'SELECT COUNT(*) FROM ' + ident(t) + ' c LEFT JOIN ' + ident(parent)
                  + ' p ON c.' + ident(child) + '=p.' + ident(parent_col)
                  + ' WHERE c.' + ident(child) + ' IS NOT NULL AND p.' + ident(parent_col) + ' IS NULL')
        for expression in re.findall(r'CONSTRAINT `[^`]+` CHECK (.*?)(?:,?\n|\n\))', schema[t]):
            check(t + ' CHECK', 'SELECT COUNT(*) FROM ' + ident(t) + ' WHERE NOT (' + expression.rstrip(',') + ')')
    sql = (Path(__file__).with_name('validate_mock_data.sql')).read_text(encoding='utf-8')
    sql = re.sub(r'--[^\n]*', '', sql)
    for index, statement in enumerate(sql.split(';')):
        if statement.strip():
            check('business-' + str(index), statement)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    a = args_parse()
    schema = load_schema(a.dump)
    LOG.info('Dump SHA256=%s; seed=%s; run-tag=%s; as-of UTC=%s; mode=%s',
             hashlib.sha256(a.dump.read_bytes()).hexdigest(), a.seed, a.run_tag, a.as_of, a.mode)
    if a.offline:
        LOG.warning('Offline estimate only: MOVIE_COUNT=%s is not a verified live count', a.movie_count)
        plan(a, a.movie_count)
        return 0
    conn = connect(a)
    locked = False
    try:
        with conn.cursor() as q:
            preflight(q, schema)
            # Advisory lock coordinates copies of this script only, not the application.
            q.execute("SELECT GET_LOCK(CONCAT('mock-seed:',DATABASE()), 0)")
            locked = q.fetchone()[0] == 1
            if not locked:
                raise ValueError('Another seed run is active')
            q.execute('SELECT COUNT(*), COALESCE(SUM(deleted_at IS NULL),0) FROM movieinfo')
            total, available = map(int, q.fetchone())
            LOG.info('Live movieinfo total=%s active=%s', total, available)
            if not available:
                raise ValueError('No active movies; movie-count cannot create referenced movies')
            shape = plan(a, available)
            before = {}
            for t in TABLES:
                q.execute('SELECT COUNT(*) FROM ' + ident(t))
                before[t] = q.fetchone()[0]
            LOG.info('Existing counts=%s', json.dumps(before))
            if not a.execute:
                LOG.info('Read-only plan complete; use --execute to write')
                return 0
            q.execute('SELECT movieid,moviename,averating FROM movieinfo WHERE deleted_at IS NULL ORDER BY movieid')
            movies = q.fetchall()
            if a.mode == 'rebuild':
                # DELETE is transactional. TRUNCATE, FK disabling and AUTO_INCREMENT resets are forbidden.
                for t in DELETE_ORDER:
                    q.execute('DELETE FROM ' + ident(t))
                    LOG.info('Deleted all rows from %s (not committed)', t)
            inserted = generate(a, q, movies, shape)
            for t in TABLES:
                q.execute('SELECT COUNT(*) FROM ' + ident(t))
                expected = inserted[t] + (before[t] if a.mode == 'append' else 0)
                if q.fetchone()[0] != expected:
                    raise ValueError('Row count mismatch: ' + t)
            validate(q, schema)
            if a.rollback_test:
                conn.rollback()
                for t in TABLES:
                    q.execute('SELECT COUNT(*) FROM ' + ident(t))
                    if q.fetchone()[0] != before[t]:
                        raise ValueError('Rollback row count mismatch: ' + t)
                LOG.info('ROLLBACK TEST PASSED; original counts restored; inserted counts=%s', json.dumps(inserted))
            else:
                conn.commit()
                LOG.info('COMMITTED inserted counts=%s', json.dumps(inserted))
    except BaseException as exc:
        try:
            conn.rollback()
        except Exception:
            # A lost connection cannot acknowledge ROLLBACK. Closing it makes
            # MySQL discard an uncommitted transaction; verify before rerunning.
            LOG.error('Rollback acknowledgement unavailable; verify server transaction state')
        # Never print connection URL, passwords or arbitrary SQL row values.
        LOG.error('ROLLED BACK: %s', type(exc).__name__)
        if isinstance(exc, ValueError):
            LOG.error('%s', exc)
        elif getattr(exc, 'args', None) and isinstance(exc.args[0], int):
            LOG.error('MySQL error code=%s (1451 usually means non-target references block rebuild)', exc.args[0])
        return 1
    finally:
        if locked and conn.open:
            try:
                with conn.cursor() as q:
                    q.execute("SELECT RELEASE_LOCK(CONCAT('mock-seed:',DATABASE()))")
            except Exception:
                LOG.error('Lock release acknowledgement unavailable; connection close releases the lock')
        conn.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as error:
        LOG.error('Cannot start: %s; check file/dependencies/connection/arguments', type(error).__name__)
        sys.exit(1)
