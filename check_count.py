import os, pymysql
try:
    conn = pymysql.connect(
        host='mariadb', 
        user='justnews', 
        password='dev_justnews_password', 
        database='justnews'
    )
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM articles')
    count = cursor.fetchone()[0]
    with open('current_count.txt', 'w') as f:
        f.write(str(count))
except Exception as e:
    with open('current_count.txt', 'w') as f:
        f.write(f"Error: {str(e)}")
