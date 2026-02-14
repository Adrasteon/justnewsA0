import mysql.connector
import os
try:
    conn = mysql.connector.connect(host='mariadb', user='justnews', password='dev_justnews_password', database='justnews')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM articles WHERE analyzed=1")
    count = cursor.fetchone()[0]
    with open('/app/status.txt', 'w') as f:
        f.write(f"Analyzed Count: {count}")
except Exception as e:
    with open('/app/status.txt', 'w') as f:
        f.write(f"Error: {e}")
