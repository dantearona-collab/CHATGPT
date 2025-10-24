### `backend/db_init.py`
# Script para inicializar la BD SQLite a partir de properties.json
import sqlite3
import json
import os

HERE = os.path.dirname(__file__)
DB = os.path.join(HERE, 'propiedades.db')
JSON = os.path.join(HERE, 'properties.json')

with open(JSON, 'r', encoding='utf-8') as f:
    props = json.load(f)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('''
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    neighborhood TEXT,
    price INTEGER,
    rooms INTEGER,
    sqm INTEGER,
    description TEXT
)
''')

cur.execute('DELETE FROM properties')
for p in props:
    cur.execute('INSERT INTO properties (title, neighborhood, price, rooms, sqm, description) VALUES (?, ?, ?, ?, ?, ?)',
                (p['title'], p['neighborhood'], p['price'], p['rooms'], p['sqm'], p['description']))

conn.commit()
conn.close()
print('DB inicializada en', DB)
