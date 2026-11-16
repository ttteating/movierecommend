import asyncio
import sys
sys.path.insert(0, 'D:\\program\\movie_recommend\\backend')
from app.database import init_db, DATABASE_URL, TORTOISE_ORM

async def main():
    print('DATABASE_URL=', DATABASE_URL)
    print('TORTOISE_ORM=', TORTOISE_ORM)
    try:
        await init_db()
        print('Tortoise initialized OK')
        try:
            from tortoise import Tortoise
            db = Tortoise.get_connection('default')
            print('connection client=', db.client)
            q = 'SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME IN (\'movierecommend_test\', \'movierecommend\')'
            rows = await db.execute_query(q)
            print('available dbs=', [r[0] for r in rows])
            tables = await db.execute_query('SHOW TABLES;')
            print('all tables=', [r[0] for r in tables])
        except Exception as e:
            print('db query failed:', repr(e))
        finally:
            await Tortoise.close_connections()
    except Exception as e:
        print('init_db failed:', repr(e))

asyncio.run(main())
