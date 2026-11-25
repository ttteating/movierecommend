"""Read-only checks for the configured recommendation database and grants."""

from __future__ import annotations

import asyncio
from urllib.parse import unquote, urlsplit

import asyncmy
from dotenv import dotenv_values


REQUIRED_TABLES = {"personalratings", "user", "movieinfo", "recommendationitem"}


async def inspect_connection(host, port, user, password, database) -> tuple[dict[str, int], list[str]]:
    connection = await asyncmy.connect(
        host=host, port=port, user=user, password=password,
        database=database, connect_timeout=5, autocommit=True,
    )
    try:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT DATABASE()")
            schema = (await cursor.fetchone())[0]
            await cursor.execute(
                "SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s,%s,%s)",
                [database, *sorted(REQUIRED_TABLES)],
            )
            table_stats = {row[0]: row[1] for row in await cursor.fetchall()}
            await cursor.execute("SHOW GRANTS")
            grants = [row[0].upper() for row in await cursor.fetchall()]
            return table_stats, grants
    finally:
        connection.close()


async def check() -> int:
    config = dotenv_values(".env")
    raw_url = config.get("DATABASE_URL")
    if not raw_url:
        print("database_url_configured=False")
        return 1

    parsed = urlsplit(raw_url)
    expected_schema = unquote(parsed.path.lstrip("/"))
    if expected_schema != "movierecommend_new":
        print("configured_schema_is_movierecommend_new=False")
        return 1
    try:
        table_stats, grants = await inspect_connection(
            parsed.hostname, parsed.port or 3306,
            unquote(parsed.username or ""), unquote(parsed.password or ""),
            expected_schema,
        )
    except Exception as exc:
        code = exc.args[0] if getattr(exc, "args", None) else type(exc).__name__
        print(f"database_connection=False mysql_error_code={code}")
        return 1

    try:
        tables = set(table_stats)
        all_privileges = any("ALL PRIVILEGES" in grant for grant in grants)
        select_granted = all_privileges or any(
            "SELECT" in grant and ("*.*" in grant or expected_schema.upper() in grant)
            for grant in grants
        )
        print(f"connected_schema={expected_schema}")
        print(f"required_tables_present={','.join(sorted(tables))}")
        print(f"required_tables_missing={','.join(sorted(REQUIRED_TABLES - tables))}")
        print("information_schema_row_estimates=" + ",".join(
            f"{table}:{table_stats[table]}" for table in sorted(table_stats)
        ))
        print(f"select_privilege_on_configured_schema={select_granted}")
    except Exception:
        raise

    jdbc_url = config.get("MYSQL_JDBC_URL")
    jdbc_user = config.get("MYSQL_USER")
    jdbc_password = config.get("MYSQL_PASSWORD")
    if jdbc_url and jdbc_user and jdbc_password:
        jdbc = urlsplit(jdbc_url.removeprefix("jdbc:"))
        try:
            _, jdbc_grants = await inspect_connection(
                jdbc.hostname, jdbc.port or 3306, jdbc_user, jdbc_password, expected_schema
            )
            jdbc_all = any("ALL PRIVILEGES" in grant for grant in jdbc_grants)
            jdbc_select = jdbc_all or any(
                "SELECT" in grant and ("*.*" in grant or expected_schema.upper() in grant)
                for grant in jdbc_grants
            )
            print(f"jdbc_read_account_select_on_configured_schema={jdbc_select}")
        except Exception as exc:
            code = exc.args[0] if getattr(exc, "args", None) else type(exc).__name__
            print(f"jdbc_database_connection=False mysql_error_code={code}")
            return 1
    else:
        print("jdbc_credentials_configured=False")

    writer_url = config.get("RECOMMENDATION_WRITE_URL")
    if writer_url:
        writer = urlsplit(writer_url)
        try:
            _, writer_grants = await inspect_connection(
                writer.hostname, writer.port or 3306,
                unquote(writer.username or ""), unquote(writer.password or ""),
                expected_schema,
            )
        except Exception as exc:
            code = exc.args[0] if getattr(exc, "args", None) else type(exc).__name__
            print(f"writer_database_connection=False mysql_error_code={code}")
            return 1
        normalized = [grant.replace("`", "") for grant in writer_grants]
        insert_scopes = set()
        for grant in normalized:
            if not grant.startswith("GRANT ") or " ON " not in grant:
                continue
            privileges, scope = grant[6:].split(" ON ", 1)
            scope = scope.split(" TO ", 1)[0]
            if "INSERT" in {privilege.strip() for privilege in privileges.split(",")}:
                insert_scopes.add(scope)
        table_scope = f"{expected_schema.upper()}.RECOMMENDATIONITEM"
        effective_insert = bool(insert_scopes & {"*.*", f"{expected_schema.upper()}.*", table_scope})
        insert_only = any(
            grant.startswith(f"GRANT INSERT ON {table_scope} ") for grant in normalized
        ) and all(
            "GRANT USAGE ON *.*" in grant
            or grant.startswith(f"GRANT INSERT ON {table_scope} ")
            for grant in normalized
        )
        print(f"writer_has_insert_on_recommendationitem={effective_insert}")
        print(f"writer_insert_only_on_recommendationitem={insert_only}")
    else:
        print("writer_url_configured=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
