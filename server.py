#!/usr/bin/env python3
"""Hyperliquid Funding Analyzer - Server with SQLite backend."""

import http.server
import json
import sqlite3
import os
import time
import urllib.parse
import urllib.request
import urllib.error

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'funding.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS market_data (
            coin TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS funding_history (
            coin TEXT PRIMARY KEY,
            history TEXT NOT NULL,
            last_update INTEGER DEFAULT 0,
            record_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS user_preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER DEFAULT 0
        );
    ''')
    conn.commit()
    conn.close()
    print(f"Database: {DB_PATH}")


class RequestHandler(http.server.SimpleHTTPRequestHandler):

    def send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(body.encode('utf-8'))
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # Client disconnected, ignore

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return None
        return json.loads(self.rfile.read(length))

    # ── GET ──────────────────────────────────────────────
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if not path.startswith('/api/'):
            return super().do_GET()

        conn = get_db()
        try:
            if path == '/api/market-data':
                rows = conn.execute('SELECT data FROM market_data').fetchall()
                self.send_json([json.loads(r['data']) for r in rows])

            elif path == '/api/funding-history':
                rows = conn.execute('SELECT coin, history FROM funding_history').fetchall()
                self.send_json({r['coin']: json.loads(r['history']) for r in rows})

            elif path == '/api/funding-history-timestamps':
                rows = conn.execute('SELECT coin, last_update FROM funding_history').fetchall()
                self.send_json({r['coin']: r['last_update'] for r in rows})

            elif path.startswith('/api/funding-history/'):
                coin = urllib.parse.unquote(path[len('/api/funding-history/'):])
                row = conn.execute(
                    'SELECT * FROM funding_history WHERE coin = ?', (coin,)
                ).fetchone()
                if row:
                    self.send_json({
                        'coin': row['coin'],
                        'history': json.loads(row['history']),
                        'lastUpdate': row['last_update'],
                        'recordCount': row['record_count']
                    })
                else:
                    self.send_json(None)

            elif path.startswith('/api/meta/'):
                key = urllib.parse.unquote(path[len('/api/meta/'):])
                row = conn.execute(
                    'SELECT value FROM metadata WHERE key = ?', (key,)
                ).fetchone()
                self.send_json({'value': json.loads(row['value']) if row else None})

            elif path == '/api/stats':
                row = conn.execute('''
                    SELECT COUNT(*) as coins,
                           COALESCE(SUM(record_count), 0) as total_records,
                           MIN(last_update) as oldest,
                           MAX(last_update) as newest
                    FROM funding_history
                ''').fetchone()
                self.send_json({
                    'coins': row['coins'],
                    'totalRecords': row['total_records'],
                    'oldestUpdate': row['oldest'],
                    'newestUpdate': row['newest']
                })

            elif path == '/api/preferences/favorites':
                row = conn.execute(
                    "SELECT value FROM user_preferences WHERE key = 'favorites'"
                ).fetchone()
                self.send_json(json.loads(row['value']) if row else [])

            elif path == '/api/preferences/blacklist':
                row = conn.execute(
                    "SELECT value FROM user_preferences WHERE key = 'blacklist'"
                ).fetchone()
                self.send_json(json.loads(row['value']) if row else [])

            elif path == '/api/preferences/newtokens':
                row = conn.execute(
                    "SELECT value FROM user_preferences WHERE key = 'newtokens'"
                ).fetchone()
                self.send_json(json.loads(row['value']) if row else [])

            else:
                self.send_json({'error': 'Not found'}, 404)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
        finally:
            conn.close()

    # ── POST ─────────────────────────────────────────────
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if not path.startswith('/api/'):
            self.send_error(404)
            return

        # Proxy para Hyperliquid API (evita CORS)
        if path == '/api/proxy':
            return self.handle_proxy()

        data = self.read_body()
        conn = get_db()
        try:
            if path == '/api/market-data':
                conn.execute('DELETE FROM market_data')
                for market in (data or []):
                    conn.execute(
                        'INSERT INTO market_data (coin, data) VALUES (?, ?)',
                        (market['coin'], json.dumps(market, ensure_ascii=False))
                    )
                conn.commit()
                self.send_json({'ok': True})

            elif path == '/api/funding-history-bulk':
                now = int(time.time() * 1000)
                for coin, history in (data or {}).items():
                    conn.execute('''
                        INSERT OR REPLACE INTO funding_history
                        (coin, history, last_update, record_count)
                        VALUES (?, ?, ?, ?)
                    ''', (coin, json.dumps(history), now, len(history)))
                conn.commit()
                self.send_json({'ok': True})

            elif path.startswith('/api/funding-history/'):
                coin = urllib.parse.unquote(path[len('/api/funding-history/'):])
                history = data.get('history', [])
                now = int(time.time() * 1000)
                conn.execute('''
                    INSERT OR REPLACE INTO funding_history
                    (coin, history, last_update, record_count)
                    VALUES (?, ?, ?, ?)
                ''', (coin, json.dumps(history), now, len(history)))
                conn.commit()
                self.send_json({'ok': True})

            elif path == '/api/meta':
                key = data.get('key')
                value = data.get('value')
                now = int(time.time() * 1000)
                conn.execute('''
                    INSERT OR REPLACE INTO metadata (key, value, updated_at)
                    VALUES (?, ?, ?)
                ''', (key, json.dumps(value), now))
                conn.commit()
                self.send_json({'ok': True})

            elif path == '/api/preferences/favorites':
                now = int(time.time() * 1000)
                conn.execute('''
                    INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
                    VALUES ('favorites', ?, ?)
                ''', (json.dumps(data), now))
                conn.commit()
                self.send_json({'ok': True})

            elif path == '/api/preferences/blacklist':
                now = int(time.time() * 1000)
                conn.execute('''
                    INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
                    VALUES ('blacklist', ?, ?)
                ''', (json.dumps(data), now))
                conn.commit()
                self.send_json({'ok': True})

            elif path == '/api/preferences/newtokens':
                now = int(time.time() * 1000)
                conn.execute('''
                    INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
                    VALUES ('newtokens', ?, ?)
                ''', (json.dumps(data), now))
                conn.commit()
                self.send_json({'ok': True})

            else:
                self.send_json({'error': 'Not found'}, 404)
        except Exception as e:
            conn.rollback()
            self.send_json({'error': str(e)}, 500)
        finally:
            conn.close()

    # ── DELETE ────────────────────────────────────────────
    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/api/data':
            conn = get_db()
            try:
                conn.execute('DELETE FROM market_data')
                conn.execute('DELETE FROM funding_history')
                conn.execute('DELETE FROM metadata')
                conn.commit()
                self.send_json({'ok': True})
            except Exception as e:
                conn.rollback()
                self.send_json({'error': str(e)}, 500)
            finally:
                conn.close()
        else:
            self.send_error(404)

    # ── PROXY ─────────────────────────────────────────────
    def handle_proxy(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length > 0 else b''

            # Parse request to get coin name for logging
            try:
                req_data = json.loads(body)
                coin = req_data.get('coin', req_data.get('dex', req_data.get('type', 'unknown')))
            except:
                coin = 'unknown'

            # Retry logic for transient errors
            max_retries = 5
            last_error = None

            for attempt in range(max_retries):
                try:
                    req = urllib.request.Request(
                        'https://api.hyperliquid.xyz/info',
                        data=body,
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        result = resp.read()
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Cache-Control', 'no-cache')
                        self.end_headers()
                        self.wfile.write(result)
                        return  # Success, exit
                except urllib.error.HTTPError as e:
                    last_error = e
                    print(f"[PROXY] {coin} - HTTP {e.code} (attempt {attempt + 1}/{max_retries})")
                    if e.code in (502, 503, 504) and attempt < max_retries - 1:
                        delay = 1.0 * (attempt + 1)  # 1s, 2s, 3s, 4s
                        time.sleep(delay)
                        continue
                    raise
                except urllib.error.URLError as e:
                    last_error = e
                    print(f"[PROXY] {coin} - URLError: {e.reason} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        delay = 1.0 * (attempt + 1)
                        time.sleep(delay)
                        continue
                    raise

        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # Client disconnected, ignore
        except Exception as e:
            print(f"[PROXY] {coin} - FAILED: {e}")
            self.send_json({'error': str(e)}, 502)

    def log_message(self, format, *args):
        if args and '/api/' in str(args[0]):
            super().log_message(format, *args)


if __name__ == '__main__':
    init_db()
    PORT = 8000
    server = http.server.HTTPServer(('', PORT), RequestHandler)
    print(f'Hyperliquid Funding Analyzer')
    print(f'http://localhost:{PORT}')
    print(f'Ctrl+C to stop')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
        server.server_close()
