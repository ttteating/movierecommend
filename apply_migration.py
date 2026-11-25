import pymysql

conn = pymysql.connect(host='localhost', user='root', password='123456', database='movierecommend')
cur = conn.cursor()

# Add deleted_at column to moviecategory table if not exists
cur.execute("ALTER TABLE moviecategory ADD COLUMN deleted_at datetime(6) NULL")
conn.commit()

print("Column 'deleted_at' added to moviecategory table successfully")

# Verify the column was added
cur.execute("DESCRIBE moviecategory")
for row in cur.fetchall():
    print(row)

conn.close()